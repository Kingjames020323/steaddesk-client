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


def adb(*args, data=None):
    return subprocess.run(
        ["adb", *args], input=data, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=30, check=True,
    ).stdout.decode()


def shell(*args, data=None):
    return adb("shell", "-T", shlex.join(args), data=data)


def app_file(*args):
    return shell("run-as", PACKAGE, *args)


def expect_status(expected):
    result = shell("content", "query", "--uri", STATUS).strip()
    assert result == f"Row: 0 password_set={str(expected).lower()}", "Unexpected status row"


def write(data, uri=PASSWORD):
    return shell("content", "write", "--uri", uri, data=data)


def check_state(expected):
    # Each accepted native-store call appends its one-byte fixture label.
    assert app_file("cat", "files/state") == expected, "Unexpected store calls or payload"


def switch_adbd(root):
    adb("root" if root else "unroot")
    adb("wait-for-device")
    assert shell("id", "-u").strip() == ("0" if root else "2000")


def wait_for_store():
    deadline = monotonic() + 5
    while True:
        try:
            app_file("test", "-e", "files/entered")
            break
        except subprocess.CalledProcessError:
            assert monotonic() < deadline, "Store did not start"
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
    expect_status(True)
    check_state("A")
    for payload in (b"A" * 19, b"A" * 21, b"A" * 19 + b"0", b"A" * 20 + b"\r\n",
                    b"A" * 20 + b"\n\n", b"A" * 19 + b"\xff", b""):
        write(payload)
        expect_status(False)
        check_state("A")
    print("PASS shell write, status shape, and invalid rotations preserve saved fixture", flush=True)

    # Suspend a valid rotation inside the native-store seam. An old true result
    # must never acknowledge a pending write before that write has committed.
    write(b"A" * 20)
    expect_status(True)
    app_file("touch", "files/hold")
    write(b"z" * 20 + b"\n")
    wait_for_store()
    assert "FileNotFoundException: busy" in write(b"A" * 20), "Concurrent write was not rejected"
    with subprocess.Popen(["adb", "shell", "-T", "content", "query", "--uri", STATUS],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as query:
        try:
            # Give the independent Binder call time to observe the pending state.
            try:
                early = query.communicate(timeout=0.75)[0]
            except subprocess.TimeoutExpired:
                pass
            else:
                raise AssertionError(f"Query returned before commit: {early!r}")
        finally:
            app_file("rm", "files/hold")
        row = query.communicate(timeout=10)[0].decode().strip()
        assert query.returncode == 0 and row == "Row: 0 password_set=true", repr(row)
    check_state("AAz")
    print("PASS query waits for rotation commit and accepts single trailing LF", flush=True)

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
    wait_for_store()
    shell("am", "force-stop", PACKAGE)
    expect_status(False)
    check_state("AAz")
    app_file("rm", "files/hold")
    print("PASS interrupted rotation survives process death without acknowledging old value", flush=True)
    switch_adbd(True)
    write(b"A" * 20)
    expect_status(True)
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
