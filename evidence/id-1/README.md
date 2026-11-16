# Grouped device IDs

Flutter 3.24.5 rendered these PNGs on a headless test surface with synthetic peers and the product language catalogs. The merchant capture shows the Android-layout home page. The other images show the Windows-layout Devices directory, Recent connections directory and ready-session header. Each PNG contains the rendered surface at its original dimensions.

| Surface | English | 简体中文 | Español |
| --- | --- | --- | --- |
| Merchant home, 820 × 400 | [English](merchant-en.png) | [简体中文](merchant-zh-cn.png) | [Español](merchant-es.png) |
| Devices, 980 × 246 | [English](devices-en.png) | [简体中文](devices-zh-cn.png) | [Español](devices-es.png) |
| Recent connections, 980 × 246 | [English](recent-en.png) | [简体中文](recent-zh-cn.png) | [Español](recent-es.png) |
| Connected-session header, 1000 × 52 | [English](session-en.png) | [简体中文](session-zh-cn.png) | [Español](session-es.png) |

The directory shows both fixture IDs, `123 456 789` and `1 234 567 890`. The merchant and session views show the ten-digit ID. The Spanish support catalog uses English fallback for some existing directory labels, including “Devices” and “Recent connections”.

The capture exercised `MerchantPanel`, the production directory for each page, and the session header with `ready` set by the fixture. The native bridge supplied the peer data, simulated readiness and translation lookups. Desktop window captions were checked as strings. Hardware, remote connections, platform screen-reader audio and native window rendering remain outside this evidence.
