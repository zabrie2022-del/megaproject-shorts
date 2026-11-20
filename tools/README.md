# Tools for building the Shorts

Every video for this channel must have sound. These scripts build a 21-second vertical Short
(1080x1920, 30 fps) with animated graphics and an original music track.

## Files

- `shorts.py`: drawing and rendering functions (`make_bg`, `frame`, `render`, `SCENES`).
- `music.py`: generates an original backing track as a WAV file. `python3 music.py out.wav 21 SEED`
- `example_batch.py`: shows how to define videos and render them.

## How to build a batch

1. Copy `example_batch.py` to a new file and replace the `b.VIDEOS` dictionary with new topics.
   Each video needs: `accent`, `bar`, `track`, `card`, `bg`, `layout` ("grid" or "list"), `hero`,
   `unit`, `headline`, `sub`, `question`, `row_unit`, `rows`, `caption`, `name`, `place`, `facts`
   (four pairs) and `closing` (three lines). Use a different colour scheme for each video.
2. Draw preview frames and look at them: `python3 my_batch.py preview OUT_DIR`
3. Render: `python3 my_batch.py full OUT_DIR`
4. Add music to every video, with a different SEED for each:

   ```
   python3 music.py OUT_DIR/NAME.wav 21 SEED
   ffmpeg -y -i OUT_DIR/NAME.mp4 -i OUT_DIR/NAME.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 160k -shortest FINAL/NAME.mp4
   ```

5. Check that each final file has an audio stream before using it:
   `ffprobe -v error -select_streams a -show_entries stream=codec_name -of csv=p=0 FINAL/NAME.mp4`

Needs Python with Pillow and numpy, ffmpeg, and the Poppins fonts in
`/usr/share/fonts/truetype/google-fonts/`.

## Hook and ending (changed 20 Nov 2026)

- The opening scene shows the big number and headline on the very first frame. To show words instead
  of a plain number, add `hook_text="$62 BILLION"` to the video (it replaces `hero` and `unit` on screen).
- The last scene ends with "Subscribe for more megaprojects".
