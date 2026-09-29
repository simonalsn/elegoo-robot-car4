# Dashboard visual prototype

Open index.html directly in a browser. It is self-contained, uses no external
assets, and never connects to the robot or reads a controller. The room is an
inline SVG illustration, not live video. All telemetry is illustrative; wheel
PWM examples correspond to the current mixer at the displayed raw inputs.

Use the Preview state selector to compare Driving, Ready, blocked states and
Stopped. Stop and Space affect the preview only. Resume simulates neutral input.
The camera-target button changes the indicator, not the illustrated scene.

Proposed layout: dominant 4:3 video with unobtrusive centre mark, status and stop
at top right, requested inputs and wheel outputs below, connection health beneath
video, and a compact control guide. This is a design reference for the existing
pygame client, not a replacement architecture or an implemented safety feature.
Space-to-stop and explicit resume are proposals. Calibrated path/width overlays
are deferred. No firmware or driving-code changes were made for this mockup.
