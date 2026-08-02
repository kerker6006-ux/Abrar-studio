# Abrar Studio 3.0.0 verification report

## Result

Abrar Studio 3.0.0 passed three fresh local verification cycles after the articulated puppet, walk/run, footstep and motion-template upgrade.

Each cycle completed:

- **37 automated tests passed**
- **1 display-only UI smoke test skipped** in the headless Linux environment
- **13/13 release-render checks passed**

The skipped UI test is designed to execute when a graphical desktop is available. The Windows installer repeats the full suite on the target PC.

## Articulated motion checks

Both Seo-yeon and Min-jun were verified to contain:

- checksum-locked articulated rig definitions
- head and torso hierarchy
- independent front/back upper arms and forearms
- independent front/back thighs, lower legs and feet
- supported walk/run/start/stop/recoil motion names
- distinct generated walk and run frames
- left/right facing support
- automatic gait-derived footstep timestamps

The release episode exercised:

- confident walking with horizontal travel
- sudden stopping
- paired running with different cycle offsets
- automatic footstep insertion
- tracking/panning camera
- Korean mouth timing from synthetic verification WAV files
- music, ambience, timed SFX, subtitles and final mixing

## Media checks passed on all three cycles

1. Quality gates
2. Articulated rigs
3. Walk/run template
4. Output file exists
5. Output size exceeds 100 KB
6. Width is 1280
7. Height is 720
8. Video codec is H.264
9. Audio codec is AAC
10. Frame rate is constant 24 FPS
11. Audio sample rate is 48 kHz
12. Duration matches the episode timeline
13. Secret/API-key scan is clean

## Visual review

The 7.085-second articulated motion demonstration was reviewed through extracted frames. It shows Seo-yeon walking, stopping, and running with Min-jun in the same limited cutout/bone-rig style targeted from the supplied reference video.

## Environment boundary

The native `AbrarStudio-Setup.exe` must be built or run on Windows. This Linux environment verified the source installer, Python application, assets, renderer and encoded videos, but cannot execute a Windows installer or make a paid live Gemini request. Abrar Studio includes a post-install **Test Gemini** function for the replacement API key.
