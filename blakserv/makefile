#
# makefile for blakserv
#

TOPDIR=..
!include $(TOPDIR)\common.mak

# ----------------------------------------------------------------------
# Additional compiler flags (see common.mak)
# /TP           Compile as C++ code
# /arch:SSE2    Use SSE2 instructions (VS2013+ default to SSE2)
CFLAGS = $(CFLAGS) /arch:SSE2 /TP /Zi

# ----------------------------------------------------------------------
# Additional linker flags (see common.mak)
# /SUBSYSTEM:WINDOWS",5.01" UI Windows XP (5.01)
# /STACK  Stacksize in bytes
# /map    Generate mapfile
LINKFLAGS = $(LINKFLAGS) /SUBSYSTEM:WINDOWS",5.01" /STACK:0x180000 /map /DEBUG

SOURCEDIR = .

LIBS = gdi32.lib user32.lib wsock32.lib winmm.lib comctl32.lib libmysql.lib libcurl.lib ws2_32.lib jansson.lib

OBJS =  \
    $(OUTDIR)\main.obj \
    $(OUTDIR)\main_windows.obj \
    $(OUTDIR)\loadkod.obj \
    $(OUTDIR)\class.obj \
    $(OUTDIR)\message.obj \
    $(OUTDIR)\object.obj \
    $(OUTDIR)\sendmsg.obj \
    $(OUTDIR)\roofile.obj \
    $(OUTDIR)\bufpool.obj \
    $(OUTDIR)\ccode.obj \
    $(OUTDIR)\channel.obj \
    $(OUTDIR)\list.obj \
    $(OUTDIR)\timer.obj \
    $(OUTDIR)\session.obj \
    $(OUTDIR)\loadrsc.obj \
    $(OUTDIR)\blakres.obj \
    $(OUTDIR)\roomdata.obj \
    $(OUTDIR)\commcli.obj \
    $(OUTDIR)\string.obj \
    $(OUTDIR)\async.obj \
    $(OUTDIR)\async_windows.obj \
    $(OUTDIR)\loadgame.obj \
    $(OUTDIR)\game.obj \
    $(OUTDIR)\term.obj \
    $(OUTDIR)\account.obj \
    $(OUTDIR)\loadacco.obj \
    $(OUTDIR)\saveacco.obj \
    $(OUTDIR)\savestr.obj \
    $(OUTDIR)\loadstr.obj \
    $(OUTDIR)\nameid.obj \
    $(OUTDIR)\time.obj \
    $(OUTDIR)\dllist.obj \
    $(OUTDIR)\trysync.obj \
    $(OUTDIR)\saveall.obj \
    $(OUTDIR)\loadall.obj \
    $(OUTDIR)\synched.obj \
    $(OUTDIR)\motd.obj \
    $(OUTDIR)\admin.obj \
    $(OUTDIR)\garbage.obj \
    $(OUTDIR)\kodbase.obj \
    $(OUTDIR)\savegame.obj \
    $(OUTDIR)\user.obj \
    $(OUTDIR)\system.obj \
    $(OUTDIR)\resync.obj \
    $(OUTDIR)\gamelock.obj \
    $(OUTDIR)\config.obj \
    $(OUTDIR)\apndfile.obj \
    $(OUTDIR)\admincons.obj \
    $(OUTDIR)\builtin.obj \
    $(OUTDIR)\version.obj \
    $(OUTDIR)\systimer.obj \
    $(OUTDIR)\memory.obj \
    $(OUTDIR)\interface_windows.obj \
    $(OUTDIR)\intrlock.obj \
    $(OUTDIR)\chanbuf.obj \
    $(OUTDIR)\debug.obj \
    $(OUTDIR)\saversc.obj \
    $(OUTDIR)\adminfn.obj \
    $(OUTDIR)\table.obj \
    $(OUTDIR)\parsecli.obj \
    $(OUTDIR)\rscload.obj \
    $(OUTDIR)\crc.obj \
    $(OUTDIR)\md5.obj \
    $(OUTDIR)\maintenance.obj \
    $(OUTDIR)\block.obj \
    $(OUTDIR)\stringinthash.obj \
    $(OUTDIR)\intstringhash.obj \
    $(OUTDIR)\files.obj \
    $(OUTDIR)\sprocket.obj \
    $(OUTDIR)\mutex_windows.obj \
    $(OUTDIR)\thdmsgqueue_windows.obj \
    $(OUTDIR)\database.obj \

all : makedirs $(OUTDIR)\blakserv.exe

$(OUTDIR)\rscload.obj : $(TOPDIR)\util\rscload.c
    $(CC) -Fo$(OUTDIR)/ $(CFLAGS) /Fd$(OUTDIR)\ /FpCpch -c $**

$(OUTDIR)\crc.obj : $(TOPDIR)\util\crc.c
    $(CC) -Fo$(OUTDIR)/ $(CFLAGS) /Fd$(OUTDIR)\ /FpCpch -c $**

$(OUTDIR)\md5.obj : $(TOPDIR)\util\md5.c
    $(CC) -Fo$(OUTDIR)/ $(CFLAGS) /Fd$(OUTDIR)\ /Fpmd5pch -c $**

$(OUTDIR)\blakserv.exe: $(OBJS) $(OUTDIR)\blakserv.res
    $(CC) $(CFLAGS) -Fo$(OUTDIR)/ /FpCpch /Fd$(OUTDIR)\ -c $(SOURCEDIR)\version.c
    $(LINK)	$** $(LIBS) -OUT:$@ $(LINKFLAGS)
    $(CP) $@ $(BLAKSERVRUNDIR)
    $(CP) $(OUTDIR)\*.pdb $(BLAKSERVRUNDIR) >nul
    $(CP) $(OUTDIR)\*.map $(BLAKSERVRUNDIR) >nul
    $(CP) $(BLAKLIBDIR)\libmysql.dll $(BLAKSERVRUNDIR) >nul
    $(CP) $(BLAKBINDIR)\libcurl.dll $(BLAKSERVRUNDIR) >nul

!include $(TOPDIR)\rules.mak
