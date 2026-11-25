# Vigilo — user guide

## Installation

1. Unzip the `Vigilo` folder anywhere (for example `C:\Vigilo`).
2. Run `Vigilo.exe`. To create a desktop shortcut: right-click the exe → *Show more options* →
   *Send to* → *Desktop*. If Windows shows "Windows protected your PC": *More info* → *Run anyway*.
3. At the first start choose the language (English or Italian). You can change it later in
   **Settings**.
4. The program opens only once: if it is already running, starting it again brings its window to
   the front (also when it is hidden in the notification area).

## Adding cameras

- Press the **magnifier** (Find cameras): it finds the cameras and their open ports.
  **Add** picks the right connection type automatically.
- Or press **+** and type the IP address.
- Connection types:

  | Type | When |
  |---|---|
  | ICSee · RTSP | Port 554 open — the lightest |
  | ICSee · Native | Port 34567 — the ICSee app protocol |
  | ICSee · Cloud | Cameras in another house, by serial number (experimental, see the README) |
  | Other RTSP | Any camera with an `rtsp://` address |

- User: usually `admin`. Password: the one set in the ICSee app (empty if never set).
- **Test connection** checks everything, switches type if needed and detects motorized cameras
  and audio.

## Live view

- **Grid** adapts to the number of cameras and to the window. **Focus**: the selected camera big,
  the others around (click a camera to make it big).
- **Double-click** a video to enlarge it in high quality; **Esc** goes back.
- **F11** (or the arrows button): full screen with the videos only; Esc to exit.
- Moving the mouse over a video shows buttons: enlarge, snapshot, **listen**, record.
- Orange border and the **MOTION** label: the camera saw movement.
- At the top: CPU, RAM and disk use (whole PC and Vigilo alone).

## Live audio

- Press the **speaker** button on a video, or **Listen** in the toolbar, or right-click → *Listen*.
- One camera at a time; press again (**Mute**) to stop. The video shows the green **AUDIO** label.
- No sound? The camera may have no microphone, or audio may be off in its settings
  (ICSee app → camera settings → audio).

## Motorized cameras

- Move the mouse over the video: the direction pad appears at the bottom left. Hold an arrow to
  move, release to stop. With the camera selected or enlarged, the keyboard arrows work too.
- **Positions**: save the current position with a name (e.g. "Gate") and go back to it with one click.

## Playback (Playback button)

- Choose the camera and the day in the calendar (days with recordings are highlighted).
- The bar at the bottom is the day: blue = recorded, orange = motion. Click a point to see exactly
  that moment. Mouse wheel = zoom (or 24 h / 4 h / 1 h / 10 min).
- **Go to**: type a time (e.g. 14:30) and press Enter.
- Speed 1x … 16x. Space = play/pause, arrows = 10 seconds.
- **Motion events** list: click one to watch it.
- **Speaker** button: recorded audio (at 1x speed).
- **Snapshot** saves the picture at full resolution; **Export** saves an MP4 clip (30 s … 30 min) in
  the `Exports` folder, ready for WhatsApp or a USB stick.

## Recording and overwrite (Settings)

- Recordings are in `Videos\Vigilo\<camera name>\` (changeable).
- **Recording mode**
  - *Continuous*: records all the time, in files of 5 / 10 / 15 / 30 minutes.
  - *Only on motion*: keeps only what happens from a few seconds before a motion until the chosen
    number of minutes after the last motion. Files are 1 minute long. The tiles show **ARMED** while
    waiting for motion and **REC** while keeping. Cameras with motion detection off record continuously.
- **Record audio too**: also stores the camera's audio when it has a microphone.
- **Automatic overwrite**: when a limit is reached the oldest recordings are deleted to make room:
  maximum space (GB), days to keep, minimum free space on the disk (GB).
- Recording happens **only while the program is running**. Closing the window does not stop it:
  Vigilo keeps running in the **notification area** (the icon next to the clock). To really close it:
  right-click the icon → *Quit Vigilo*. You can change this in *Settings → Startup and background*.
- While it records, Vigilo **keeps the PC awake** (the screen can still turn off). A sleep you choose
  yourself (Start menu, power button, closing a laptop lid) still happens.
- Turn on *Start the program when the PC starts* so it starts recording again after a reboot.
- *Settings → Performance → Video decoding on the graphics card*: **Automatic** (default) decodes the
  video on the graphics card, which leaves more CPU free, above all in the enlarged view and in
  playback; the camera card shows "· GPU". Choose
  **Off** only if the picture shows problems: the CPU then does everything, as before.
- If Vigilo stops because of an error it is **started again automatically** after a few seconds and
  says so with a message. If it keeps failing it stops trying and tells you; the details are in
  `%APPDATA%\Vigilo\vigilo.log`.

## Files and folders

| Where | What |
|---|---|
| `%APPDATA%\Vigilo\config.json` | Settings and cameras (passwords included, in plain text) |
| `<recordings>\<camera>\*.mkv` | Recordings |
| `<recordings>\<camera>\events\` | Motion events (one file per day) |
| `<recordings>\<camera>\Snapshots\` | Snapshots |
| `<recordings>\Exports\` | Exported clips |

## Safety tips

These cameras have known vulnerabilities (for example anyone on your network can read their Wi-Fi
password). Keep them on a separate network (guest Wi-Fi or VLAN), never open their ports on the
router, and give every camera its own password.
