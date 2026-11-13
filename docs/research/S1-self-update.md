# S1 · 商米商户版能否无人操作地更新自己

**Jason 真机结果（2026-11-13）。** OrderPAD 3 和 D3 PRO 各做一次升级、一次同版本重装，四次均静默成功，录屏自动恢复。现场没有演练服务器，客服端 120 秒内取得实时首帧的用时未测。

 测试对象是没有 Device Owner 权限的 SteadDesk。每台设备做两轮，第一轮从 N 升到 N+1，第二轮再提交同一份 N+1 APK。系统安装回调、设备实际显示的界面、客服能否恢复画面各自记一项。

## 上游依据

- Android 12 起，具有安装来源授权的安装方自更新时，可以请求 `USER_ACTION_NOT_REQUIRED`。还须声明 `UPDATE_PACKAGES_WITHOUT_USER_ACTION`，待装应用在 Android 13 的 target 至少为 30，在 Android 14 至少为 31。本次两个 APK 的 target 都是 36。安装器仍须处理 `STATUS_PENDING_USER_ACTION`。[SessionParams.setRequireUserAction](https://developer.android.com/reference/android/content/pm/PackageInstaller.SessionParams#setRequireUserAction(int)) · [检查安装来源授权](https://developer.android.com/reference/android/content/pm/PackageManager#canRequestPackageInstalls())
- S1 在应用 UID 下创建、写入、同步并提交安装会话。系统通过可变、显式指向本应用私有接收器的 PendingIntent 回传状态。两台商米的固件可能对后台确认窗口采取不同策略，日志和屏幕分别保留。[Session.commit](https://developer.android.com/reference/android/content/pm/PackageInstaller.Session#commit(android.content.IntentSender)) · [安装状态和确认 Intent](https://developer.android.com/reference/android/content/pm/PackageInstaller#STATUS_PENDING_USER_ACTION)
- 包替换广播进入商户版已有开机路径。它检查电池优化及悬浮窗权限，显示启动 Toast，启动 MainService；服务收到启动标志后恢复服务并按原流程请求录屏。即使安装静默，也可能出现录屏确认或没有可用画面。[Android 包替换广播](https://developer.android.com/reference/android/content/Intent#ACTION_MY_PACKAGE_REPLACED) · [RustDesk 1.5.0 BootReceiver.kt L19–44](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb/BootReceiver.kt#L19-L44) · [MainService.kt L346–364](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb/MainService.kt#L346-L364) · [已有商户开机补丁](../../patches/0011-merchant-android-boot.patch)
- Android 构建从 RELEASE_VERSION 取版本名，以 68 加末段编号作 versionCode。0015 把同源生成的 merchantVersion 放在帮助区；Jason 在商米面板底部未看到版本号。[版本补丁](../../patches/0007-release-version.patch) · [商户面板](../../patches/0015-merchant-panel.patch) · [版本选择脚本](../../scripts/configure-edition.sh)

## Jason 的真机步骤

**准备。** 在此 PR 的同一次 Actions 运行下载 `S1-merchant-self-update-pair`，解压到同一目录。内含 N（1.5.0-sd.1 / 69）、N+1（1.5.0-sd.2 / 70）、两个包的 SHA-256 和共用签名证书的 SHA-256。每次运行生成新签名，两个包一起取。使用可重新部署的实验设备或干净测试配置；若已有同包名的异签应用，保留现状并换测试设备/环境，直接卸载会丢失原有配置。

```sh
shasum -a 256 -c SHA256SUMS
for apk in SteadDesk-S1-*.apk; do
  apksigner verify --verbose --print-certs "$apk"
done
cat SIGNER-SHA256.txt
```

1. 将设备与一台可配置的测试客服端置于隔离的演练网络。实验 DNS 把 `relay.s1.test` 指向本地 hbbs/hbbr，把 `api.s1.test` 指向本地演练 API。客服端配置相同的实验服务器及其**公钥**。只使用实验账号、实验服务器和临时密码。下列命令在 Mac/Linux 主机执行，`ANDROID_SERIAL` 只选本轮设备；记录型号、Android 版本、固件、是否有其他厂商管理策略，以及 SteadDesk 不是 Device Owner。不要在公开 PR 附设备序列号。
2. 用 adb 首装 N，然后给验证包提供该实验服务的 **id_ed25519.pub**（32 字节 Ed25519 公钥的 Base64 内容）。首次开启商户面板，完成常规测试机配置，在系统设置内记录并开启「允许此来源安装应用」。记录录屏授权/实际可见画面、无障碍是否绑定、允许悬浮窗、电池优化豁免和厂商安装白名单状态。用客服真实连通、取得画面后断开，记下 N 的界面版本；没有基线连接时，两分钟恢复项填「基线不通，未测」。

   ```sh
   export ANDROID_SERIAL='<本轮实验设备序列号>'
   adb shell getprop ro.product.model
   adb shell getprop ro.build.version.release
   adb shell getprop ro.build.display.id
   adb shell dpm list-owners
   adb install SteadDesk-S1-N.apk
   adb shell content call --uri content://com.steaddesk.remote.spike --method lab-key \
     --arg "$(tr -d '\r\n' < /path/to/LAB/id_ed25519.pub)"
   adb shell appops get com.steaddesk.remote REQUEST_INSTALL_PACKAGES
   ```

3. 另开终端，选中同一设备，记录实时日志。将 N+1 写入应用缓存，等待传输命令结束，再发起 update。这个入口只接受 shell/root，安装者是商户应用；不依赖公共下载目录的读取权限。每轮顺序执行。计时从提交 update 开始，屏幕保持可见，全程不触碰商米。

   ```sh
   # 终端一，在本轮操作前启动；保存在本地实验目录
   adb logcat -T 1 -v time -s SDSPIKE:I tagBootReceiver:D whichService:D AndroidRuntime:E
   # 终端二
   adb shell -T content write --uri content://com.steaddesk.remote.spike/apk < SteadDesk-S1-N-plus-1.apk
   adb shell content call --uri content://com.steaddesk.remote.spike --method update
   ```

4. 对齐同一 session ID 的 `submit` 和 `status`。记录实际显示的安装器、商米拦截、Toast 和录屏提示。0 为成功，−1 为需要用户操作；其他失败保留数值和系统提示。仅出现 submitted_session 或包替换广播，没有最终状态时写「未观察到最终回调」。收到 −1 即记「需要确认」，即便系统没有把窗口显示出来。在两分钟内由客服端发起连接，记录首次看到**实时画面**的秒数。窗口期内不重开商户 App、不点确认、不启动服务。
5. 两分钟结束后，用下面的只读检查与更新前对照，再打开商户面板核对版本。分别记录三项授权；录屏 app-op 或服务进程单独存在不足以证明已能取帧。如果第一轮需要点击，可在记录原结果后单独完成确认并注明「人工完成」，待设备确实处于 N+1 再做同版本轮。

   ```sh
   adb shell dumpsys package com.steaddesk.remote | grep -E 'version(Name|Code)='
   adb shell appops get com.steaddesk.remote PROJECT_MEDIA
   adb shell settings get secure enabled_accessibility_services
   adb shell appops get com.steaddesk.remote SYSTEM_ALERT_WINDOW
   adb shell dumpsys media_projection
   ```

6. 在 N+1 已安装且基线可连时，**原样重做步骤 3–5**，用同一份 N+1 文件，不卸载、清数据或重签。记录是否再次弹窗、回调和实际行为。若固件始终阻止第一次更新，第二轮写「未执行」并附原因。换另一台设备从步骤 1 开始。

### 回填表

以下安装耗时约计，来自 Jason 的真机回填。授权保留及录屏自动恢复由设备侧观察。安装期间无确认框、无商米拦截；安装来源或商米白名单的具体设置未单独回填。包替换后观察到「RustDesk 服务已开启」Toast。

| 设备 / 系统 | 轮次 | 安装界面 / 其他 UI | session / 状态码顺序 / 实装版本 | 120 秒内首帧（秒） | 录屏 / 无障碍 / 悬浮窗（前 → 后） | 安装来源 / 商米白名单或拦截 |
| --- | --- | --- | --- | --- | --- | --- |
| OrderPAD 3 / Android 14 / 4.5.30 | N → N+1 | 静默，无确认框 | 346715368 / 0 / N+1，约 5 秒 | 未测（无演练服务器） | 三项均保留，录屏自动恢复 | 无商米拦截 |
| OrderPAD 3 / Android 14 / 4.5.30 | N+1 → 同一 N+1 | 静默，无确认框 | 239996453 / 0 / N+1，约 3 秒 | 未测（无演练服务器） | 三项均保留，录屏自动恢复 | 无商米拦截 |
| D3 PRO / Android 13 / 4.0.78 | N → N+1 | 静默，无确认框 | 1560028814 / 0 / N+1，约 4 秒 | 未测（无演练服务器） | 三项均保留，录屏自动恢复 | 无商米拦截 |
| D3 PRO / Android 13 / 4.0.78 | N+1 → 同一 N+1 | 静默，无确认框 | 2037210608 / 0 / N+1，约 4 秒 | 未测（无演练服务器） | 三项均保留，录屏自动恢复 | 无商米拦截 |
| 其他安卓平板（Fire / onn，回填实际系统） | N → N+1 | 待测 | 待测 | 待测 | 待测 | 待测 |
| 其他安卓平板（同一台） | N+1 → 同一 N+1 | 待测 | 待测 | 待测 | 待测 | 待测 |

**Android 11 对照。** Fire OS 8 基于 Android 11（API 30），onn 请记录实际 API。API 30 上探针提交普通自更新会话，预期首先收到 `STATUS_PENDING_USER_ACTION`（−1）；人工同意后才可能收到成功（0）。系统来源限制或厂商拦截可能直接返回失败，请记录实际数值。API 31 起才请求免确认。用 `adb shell getprop ro.build.version.sdk` 区分这两条路径。[Amazon Fire OS 8](https://developer.amazon.com/docs/fire-tablets/fire-os-8.html) · [Android 安装会话参数](https://developer.android.com/reference/android/content/pm/PackageInstaller.SessionParams#setRequireUserAction(int))

**截图清单。** 每台保留 N 和 N+1 的商户面板版本、两轮中实际出现的确认/拦截/录屏界面、客服端首次有画面的时间和对应 session 的状态日志。可用外部录像记录无窗口的两分钟。回填前遮去设备 ID、序列号、账号和业务画面。

**正式功能边界。** 本分支只验证系统能力。正式更新从自有服务器下载，并在提交安装前校验受信签名及 SHA-256；正式客户端移除 adb 触发、实验公钥设置及测试域名。同版本重装在两台设备上也返回成功（0）。正式更新在提交安装会话前，须比较待装 APK 和已安装包的数值 versionCode，只有严格递增才提交，同版本跳过、低版本拒绝。状态 0 只表示该次安装成功。
