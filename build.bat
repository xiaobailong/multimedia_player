:: pyinstaller -F -w --hidden-import=loguru Player.py

rd /s/q dist
pyinstaller -D -w --clean --hidden-import=loguru --contents-directory "libs" --add-data=libs/ffmpeg/ffmpeg.exe;ffmpeg Player.py

::pyinstaller --clean Player.spec
