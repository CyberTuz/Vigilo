# sdk folder (optional — only for the experimental cloud connection)

The cloud connection ("ICSee · Cloud") needs the Xiongmai/Jftech SDK library, which is proprietary
and therefore **not included** in this repository. Put these files here (or in the `sdk` folder next
to `Vigilo.exe`):

- `NetSdk.dll` (64-bit)
- `StreamReader.dll`

Vigilo also looks for an installed VMS client under `Program Files`.

## Which version

| NetSdk.dll | Result |
|---|---|
| 4.0.9.x (shipped with VMS in 2024) | Refuses third-party cloud logins with **-12003** unless a Jftech developer account is configured (see below) |
| 4.0.8.80 (2019) | Works without a developer account, but only for cameras on the "old" cloud with a classic user/password login. Needs the **Microsoft Visual C++ 2005 Redistributable (x64)** |

Only use SDK files you are entitled to use. Third-party copies are not signed and cannot be verified.

## Developer account (for the newer DLL)

If you have your own Jftech open-platform application (developer.jftech.com), add its credentials to
the `settings` section of `%APPDATA%\Vigilo\config.json` while Vigilo is closed:

```json
"cloud_app": {"uuid": "...", "key": "...", "secret": "...", "moved": 2}
```

They are passed to `H264_DVR_InitAppInfo` before every cloud login. Do not use credentials taken from
other applications.

## Limits

Many recent cameras use a random user name or a login token kept in the owner's cloud account
("token devices"). Those cannot be reached with a plain user name and password, with any DLL version.
