:: pyinstaller -F -w --hidden-import=loguru Player.py

:: pyinstaller -D -w --hidden-import=loguru --contents-directory "libs" Player.py

pyinstaller --clean Player.spec