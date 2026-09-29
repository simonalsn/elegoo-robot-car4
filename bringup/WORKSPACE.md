# Workspace checkpoint

This directory records the source-controlled parts of the surrounding bring-up
workspace. The Python client lives at the repository root. The active local
workspace used a checkout named `upstream/` beside these files; these are copies,
not symlinks to the running workspace. Future changes to the surrounding workspace
must also update this snapshot before committing.

To recreate that layout in a **new empty directory**, clone this repository as
`upstream`, then copy `upstream/bringup/.` into its parent directory. Run `nix-shell`
from that parent and `car-setup` to install the client. Example after cloning:

```sh
cp -a upstream/bringup/. .
nix-shell
car-setup
elegoo-smartcar-control --robot-ip YOUR_ROBOT_IP --video udp --analogue-drive
```

The firmware tools use that parent as their workspace root. Obtain the official
firmware separately and follow the hardware/firmware notes before preparing images.
This is not an automatic firmware installer. Local paths, IP addresses and build
hashes in the historical notes describe the tested car, not a fresh installation.
The latest tested pair uses 38400 baud; see docs/analogue-drive.md,
docs/control-recovery.md and docs/servo-idle.md rather than earlier status entries.

Included: Nix shell, build/diagnostic scripts, firmware overlays, desktop patch
export, hardware/rollback notes, artifact hashes and interactive dashboard mockup.
Excluded: Wi-Fi credentials, generated firmware trees/binaries, stock downloads,
flash backups, raw logs/camera images, hardware photos, caches and virtualenvs.
Those private files remain in the existing local workspace; this commit does not
replace the on-disk rollback backups.

The dashboard is a visual prototype, not an implemented robot control dashboard.
Open docs/dashboard-mockup/index.html directly in a browser.
