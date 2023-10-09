Meridian 59 v2.0, February 2016
Andrew Kirmse and Chris Kirmse

Copyright 1994-2012 Andrew Kirmse and Chris Kirmse
All rights reserved.  Meridian is a registered trademark.

Before You Build
--------------
Install Visual Studio 2015 with Visual C++ Support (important).

READ FIRST: Security Modifications
--------------
This repository implemented a security feature that will require you to complete the following steps in order to build Classic and Blakserv. Without completing these steps, your client will fail to build and will fail to connect to the server.

1. Rename clientd3d/login.c-example to login.c
2. Edit login.c and look for "EXAMPLE_KEY_HERE", replace with a 16 character string such as `abcdefghijklmnop` - Save, compile.
3. Edit run/server/blakserv.cfg
4. Update your configuration file section as shown below (update the key to match the key you put in the client)
```
[Login]              
SecretKey            EXAMPLE_KEY_HERE
```

When a client connects to your server, this key is checked. If the keys do not match, the client is redirected to update and disconnected. This is to prevent hackers / recompilers from connecting to your server without knowledge of your server's key.

Play Meridian 59
--------------
This repository is for the "Server 104" version of Meridian 59.
You can create an account for this server and download the client on
the [server 104 website] (https://meridian59.us/).

License
--------------
This project is distributed under a license that is described in the
LICENSE file.  The license does not cover the game content (artwork, audio),
which are not included.

Note that "Meridian" is a registered trademark and you may not use it
without the written permission of the owners.

The license requires that if you redistribute this code in any form,
you must make the source code available, including any changes you
make.  We would love it if you would contribute your changes back to
the original source so that everyone can benefit.


What's included and not included
--------------
The source to the client, server, game code, Blakod compiler, room
editor, and all associated tools are included.  The source code to
the irrKlang audio library is not included, and the graphics and music
for Meridian 59 must be downloaded with the game client.


Build Instructions
--------------

0. Install [Microsoft Visual Studio 2015 Community Edition](https://www.visualstudio.com/en-us/downloads/download-visual-studio-vs.aspx).
During installation you will need to choose "Custom" installation and add the
C++ components to the installation, as these are not installed by default (see https://msdn.microsoft.com/en-au/library/60k1461a.aspx).
0. Download this source code, either with a git client or with the
"Download ZIP" option from your chosen repository.

### Visual Studio GUI build
0. If you prefer the Visual Studio graphical interface, open
Meridian59.sln from the root folder of the codebase. Click on the
BUILD menu and select Build Solution (or press CTRL+SHIFT+B) to build.

### Makefile build
0. Locate your Visual Studio install folder, usually something like
`"C:\Program Files (x86)\Microsoft Visual Studio 14.0"`.
Navigate to the Common folder, and then the Tools folder. Example:
`"C:\Program Files (x86)\Microsoft Visual Studio 14.0\Common7\Tools"`.
0. Create a shortcut (by right-clicking on vsvars32.bat and selecting
Create shortcut) called "Meridian Development Shell" on your desktop
or in your start menu with the following property:
Target: `%windir%\system32\cmd.exe /k "C:\Program Files (x86)\Microsoft
Visual Studio 14.0\Common7\Tools\vsvars32.bat"`
0. OPTIONAL: set the "Start In" property of your shortcut to the folder
that contains the meridian source code for ease of use.
0. Open the Meridian Development Shell and navigate to the folder
containing the source code, then enter `nmake debug=1` to compile.

Getting Started: Server
--------------
0. After compilation completes, browse to the `.\run\server` folder,
and double click `blakserv.exe` to start the server.
0. Go to the `Administration` tab on the server's interface and enter
the command: `create account admin username password email` (with your
desired username, password and email (email can be "none@none").
You will see a message saying `Created ACCOUNT 4` or similar.
0. Then create a character slot on that account with `create admin 4`,
using whichever number the previous line returned instead of 4.
0. You'll now be able to log in with this account name and password.
Be sure to "save game" from the server interface to save this new
account.

Getting Started: Client
--------------
You will need to obtain the client graphics before you can run the
client locally, which can be done by installing the server 104 classic client
from the [104 website] (https://meridian59.us/).
When this is installed, building the client (via makefile or VS
solution) will automatically copy the needed resources to the
appropriate directory. If for some reason this isn't done, copy
the files manually from the 105 client's resource directory to
your repo's `.\run\localclient\resource` directory. Running `postbuild.bat`
from the root directory of the repo will also perform the copy function.
Resources may differ between versions of Meridian 59 - if using this
repository for a different version of the game, make sure you have that
client downloaded and edit `postbuild.bat` to copy the appropriate
resources.

0. After compilation completes, the client is located at
`.\run\localclient`.
0. You can point your local client at your local server by running the
client `meridian.exe` with command line flags, like this:
`meridian.exe /U:username /W:password /H:localhost /P:5959`.
0. Building the client will generate a shortcut to `meridian.exe`,
with these flags, however if this shortcut isn't present in your
client directory, you can create it by making the shortcut,
right-clicking it and selecting Properties, and adding
`/H:localhost /P:5959` after the existing link in the `Target:` box.

Note that any time you recompile KOD code, changes need to be loaded
into your local blakserv server by clicking the 'reload system' arrow
icon, next to the 'save game' disk icon.

Third-Party Code
--------------
Meridian uses the third party libraries zlib, libarchive, libpng and jansson.
Each of these is built from source which is included in the appropriately-named
directories (libzlib, libarchive, libpng and libjansson).

README file included as README.old.
