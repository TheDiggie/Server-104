# build_mapgen.ps1 -- builds MeridianMapGenerator.exe (one file, no console) with PyInstaller.
#
#   python -m pip install --user pyinstaller      (once)
#   powershell -File roomedit/roogen/build_mapgen.ps1
#
# Output: roomedit/roogen/dist/MeridianMapGenerator.exe
# The style modules are imported by styles.py, but texture_repeats is imported lazily
# inside align.py, so all of them are named as hidden imports to be safe.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
python -m PyInstaller --noconfirm --clean --onefile --windowed --name MeridianMapGenerator `
    --paths "$here" `
    --distpath "$here\dist" --workpath "$here\build" --specpath "$here\build" `
    --hidden-import style_jungle --hidden-import style_barloque --hidden-import style_cave `
    --hidden-import style_jasper --hidden-import style_cornoth --hidden-import style_marion `
    --hidden-import style_tos --hidden-import style_kocatan --hidden-import style_victoria `
    --hidden-import style_forest --hidden-import style_feyforest --hidden-import style_mountains `
    --hidden-import style_beach --hidden-import style_desert --hidden-import style_spider `
    --hidden-import style_brax --hidden-import style_marcrypt --hidden-import style_sewer `
    --hidden-import town_building --hidden-import cave2 --hidden-import dungeon --hidden-import preview `
    --hidden-import texture_repeats `
    "$here\mapgen_app.py"
