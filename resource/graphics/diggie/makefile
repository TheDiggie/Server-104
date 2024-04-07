TOPDIR=..\..\..
!include $(TOPDIR)\common.mak

SOURCEDIR = .
OUTDIR = .

.SUFFIXES: .bbg

BGFS = neeleme.bgf neelemeX.bgf iunholyt.bgf xeoneru.bgf xeoneruX.bgf \
       pear.bgf peartree.bgf orange.bgf orangetree.bgf cookie.bgf \
       mmdrat.bgf mfdrat.bgf arrowgold.bgf brc.bgf brd.bgf brj.bgf \
       brk.bgf brl.bgf brm.bgf mugo.bgf povbeermug.bgf  tikitrib.bgf \
       earthdrag.bgf earthdragX.bgf weed.bgf weed2.bgf \
       weed3.bgf weed4.bgf weed5.bgf weed6.bgf weed7.bgf weedplant.bgf \
       bdrag.bgf bdragX.bgf povwand.bgf wand.bgf wandov.bgf \
       squidS.bgf squidT.bgf wolfmask.bgf frontman.bgf ricehat.bgf squidC.bgf \
       Knight.bgf KnightX.bgf Cknight.bgf CknightX.bgf Hknight.bgf HknightX.bgf \
       corncob.bgf cornbasket.bgf mashtaters.bgf stuffing.bgf turkey.bgf ham.bgf \
       hamslices.bgf rouladen.bgf pumpslice.bgf pumppie.bgf pecanslice.bgf \
       pecanpie.bgf indianhat.bgf indianhatF.bgf pilgrimhat.bgf pilgrimhatF.bgf \
       ogre.bgf ogreX.bgf wizardhat.bgf wizardhatF.bgf ring02.bgf minersbag.bgf \
       prism1.bgf nerushld.bgf woice.bgf iwallice.bgf sickle.bgf povsickle.bgf \
       sickleov.bgf woodaxeov.bgf povwoodaxe.bgf woodaxe.bgf skinknife.bgf \
       povskinknife.bgf skinknifeov.bgf iskinning.bgf lootboxes.bgf lootmaster.bgf \
       povspirsword.bgf spirswordov.bgf spirsword.bgf ispirsword.bgf cougarbrew.bgf

!include $(RESOURCEDIR)\copy.mak

{$(SOURCEDIR)}.bbg.bgf:
   $(MAKEBGF) -o $(OUTDIR)\$*.bgf @$*.bbg

clean:
