:: pyinstaller -F -w --hidden-import=loguru Player.py

pyinstaller -D -w --hidden-import=loguru --contents-directory "libs" --add-data=libs/ffmpeg/ffmpeg.exe;ffmpeg Player.py

::pyinstaller --clean Player.spec