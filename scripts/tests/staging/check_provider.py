"""Cross-process checks on a dedicated emulator. All inputs are synthetic fixtures."""
import shlex
import subprocess
import sys
from time import monotonic, sleep

PACKAGE = "com.steaddesk.stagingtest"
INSTRUMENT = PACKAGE + "/com.steaddesk.remote.staging.AppCaller"
PREFIX = "content://com.steaddesk.remote.staging/"
PASSWORD = PREFIX + "permanent-password"
STATUS = PREFIX + "status"


def adb(*args, data=None, timeout=30):
    return subprocess.run(
        ["adb", *args], input=data, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=timeout, check=True,
    ).stdout.decode()


def shell(*args, data=None, timeout=30):
    return adb("shell", "-T", shlex.join(args), data=data, timeout=timeout)


def app_file(*args):
    return shell("run-as", PACKAGE, *args)


def read_status(timeout):
    row = shell("content", "query", "--uri", STATUS, timeout=timeout).strip()
    assert row in ("Row: 0 password_set=false", "Row: 0 password_set=true"), "Unexpected status row"
    return row == "Row: 0 password_set=true"


def expect_status(expected):
    assert read_status(timeout=10) == expected, "Unexpected password_set value"


def wait_for_confirmation(deadline=None):
    if deadline is None:
        deadline = monotonic() + 10
    while True:
        remaining = deadline - monotonic()
        assert remaining > 0, "Write was not confirmed within ten seconds"
        if read_status(timeout=remaining):
            return
        sleep(min(0.1, remaining))


def write(data, uri=PASSWORD):
    return shell("content", "write", "--uri", uri, data=data)


def check_state(expected):
    # Each accepted native-store call appends its one-byte fixture label.
    assert app_file("cat", "files/state") == expected, "Unexpected store calls or payload"


def switch_adbd(root):
    adb("root" if root else "unroot")
    adb("wait-for-device")
    assert shell("id", "-u").strip() == ("0" if root else "2000")


def wait_for_file(path):
    deadline = monotonic() + 5
    while True:
        try:
            app_file("test", "-e", path)
            break
        except subprocess.CalledProcessError:
            assert monotonic() < deadline, f"Timed out waiting for {path}"
            sleep(0.05)


def checks():
    switch_adbd(False)
    expect_status(False)
    denied = shell("am", "instrument", "-w", INSTRUMENT)
    assert "INSTRUMENTATION_CODE: -1" in denied and "failure=" not in denied, denied
    print("PASS ordinary application UID rejected by both provider entry points", flush=True)

    for uri in (STATUS, PASSWORD + "/", PASSWORD + "?test=1", PASSWORD + "#fragment"):
        result = write(b"A" * 20, uri)
        assert "FileNotFoundException: endpoint" in result, f"Unexpected openFile result for {uri}"
    result = shell("content", "read", "--uri", PASSWORD)
    assert "FileNotFoundException: endpoint" in result, "Read access to password URI succeeded"
    expect_status(False)
    print("PASS read mode and noncanonical write URIs denied", flush=True)

    write(b"A" * 20)
    wait_for_confirmation()
    check_state("A")
    for payload in (b"A" * 19, b"A" * 21, b"A" * 19 + b"0", b"A" * 20 + b"\r\n",
                    b"A" * 20 + b"\n\n", b"A" * 19 + b"\xff", b""):
        write(payload)
        expect_status(False)
        check_state("A")
    print("PASS shell write, status shape, and invalid rotations preserve saved fixture", flush=True)

    # Begin with a confirmed credential. Keep stdin open and send no bytes
    # until an independent Binder query has observed the new unconfirmed state.
    write(b"A" * 20)
    wait_for_confirmation()
    app_file("touch", "files/hold")
    try:
        with subprocess.Popen(["adb", "shell", "-T", "content", "write", "--uri", PASSWORD],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as writer:
            try:
                wait_for_file("no_backup/staging-unconfirmed")
                assert not read_status(timeout=3), "Open pipe still reports the old confirmation"
                check_state("AA")
                output = writer.communicate(input=b"z" * 20 + b"\n", timeout=5)[0]
                assert writer.returncode == 0 and not output.strip(), "Write command failed"
            finally:
                if writer.poll() is None:
                    writer.kill()
        deadline = monotonic() + 10
        wait_for_file("files/entered")
        assert "FileNotFoundException: busy" in write(b"A" * 20), "Concurrent write was not rejected"
        assert not read_status(timeout=min(3, deadline - monotonic())), "Pending save acknowledged the old password"
        check_state("AA")
    finally:
        app_file("rm", "files/hold")
    wait_for_confirmation(deadline)
    check_state("AAz")
    print("PASS status is false before stdin and during save, then true within the ten-second poll window", flush=True)

    app_file("touch", "files/fail")
    write(b"A" * 20)
    expect_status(False)
    check_state("AAz")
    shell("am", "force-stop", PACKAGE)
    expect_status(False)
    app_file("rm", "files/fail")
    app_file("rm", "files/entered")
    app_file("touch", "files/hold")
    write(b"A" * 20)
    wait_for_file("files/entered")
    shell("am", "force-stop", PACKAGE)
    expect_status(False)
    check_state("AAz")
    app_file("rm", "files/hold")
    print("PASS interrupted rotation survives process death without acknowledging old value", flush=True)
    switch_adbd(True)
    write(b"A" * 20)
    wait_for_confirmation()
    check_state("AAzA")
    print("PASS failed-save status survives restart and root can retry", flush=True)


if __name__ == "__main__":
    # Refuse to disturb an already installed fixture, including on parallel runs.
    packages = shell("pm", "list", "packages", PACKAGE).splitlines()
    if f"package:{PACKAGE}" in packages:
        raise SystemExit("Fixture already installed on the selected emulator")
    adb("install", "-t", sys.argv[1])
    try:
        checks()
    finally:
        adb("uninstall", PACKAGE)
        switch_adbd(False)
