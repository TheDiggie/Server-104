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
       povspirsword.bgf spirswordov.bgf spirsword.bgf ispirsword.bgf cougarbrew.bgf \
       dyeremover.bgf icraftapparel.bgf icraftaxe.bgf icraftbbow.bgf icraftbrawl.bgf \
       icraftchaina.bgf icraftcirclet.bgf icraftdaemhelm.bgf icraftgaunt.bgf icraftgldshld.bgf \
       icraftgoldshld.bgf icraftham.bgf icrafthelm.bgf icraftivy.bgf icraftknightsh.bgf \
       icraftknightshld.bgf icraftlbow.bgf icraftleatha.bgf icraftlightrobe.bgf \
       icraftlongsword.bgf icraftmace.bgf icraftmagicrobe.bgf icraftmsh.bgf icraftmyssword.bgf \
       icraftnerua.bgf icraftnerubow.bgf icraftnerushld.bgf icraftnerusword.bgf icraftpickaxe.bgf \
       icraftplatea.bgf icraftscalea.bgf icraftscim.bgf icraftshortsword.bgf icraftsickle.bgf \
       icraftskinknife.bgf icraftsmallshld.bgf icraftwizardhat.bgf icraftwoodaxe.bgf hydrab.bgf \
       hydrabX.bgf hydrag.bgf hydragX.bgf hydrar.bgf hydrarX.bgf hydray.bgf hydrayX.bgf \
       seekera.bgf seekeraX.bgf seekerb.bgf seekerbX.bgf seekerc.bgf seekercX.bgf \
       chimera.bgf chimeraX.bgf croco.bgf crocoX.bgf crusher.bgf crusherX.bgf cyclops.bgf \
       cyclopsX.bgf dthmitea.bgf dthmiteaX.bgf dthmiteb.bgf dthmitebX.bgf dthmitec.bgf \
       dthmitecX.bgf dthmited.bgf dthmitedX.bgf dulahan.bgf dulahanX.bgf fallenmonk.bgf \
       fallenmonkX.bgf followerofqor.bgf followerofqorX.bgf frenzy.bgf frenzyX.bgf \
       grandpatrent.bgf grandpatrentX.bgf hellwasp.bgf hellwaspX.bgf reavera.bgf \
       reaveraX.bgf reaverb.bgf reaverbX.bgf reaverc.bgf reavercX.bgf minotaurb.bgf \
       minotaurbX.bgf snake.bgf snakeX.bgf spitter.bgf spitterX.bgf tyrant.bgf tyrantX.bgf \
       tyranthorns.bgf vajra.bgf vajraX.bgf vozun.bgf vozunX.bgf wasphive.bgf doubloon.bgf \
       dragon.bgf dragonX.bgf maul.bgf maulov.bgf povmaul.bgf neruaxe.bgf neruaxeov.bgf \
       povneruaxe.bgf povshalblade.bgf shalblade.bgf shalbladeov.bgf lightsw.bgf lightswov.bgf \
       povlightsw.bgf bersaxe.bgf bersaxeov.bgf pocbersaxe.bgf lunchbox.bgf cowX.bgf rawsteak.bgf \
       tomatoplant.bgf tomato.bgf banana.bgf cuttomato.bgf cucumber.bgf onion.bgf oats.bgf eggs.bgf \
       broccoli.bgf cornstalk.bgf earcorn.bgf watermelon.bgf watermelonslice.bgf watermelonpatch.bgf \
       carrot.bgf carrotplant.bgf potatoes.bgf potatoplant.bgf commonoats.bgf flour.bgf wheatplant.bgf \
       henhouse.bgf rawchicken.bgf GRD61042.bgf grd19081.bgf grd00101.bgf grd00102.bgf grd00103.bgf \
       grd00050.bgf grd61043.bgf grd61044.bgf zimmucas.bgf playerquiver.bgf Veydran.bgf iappraise.bgf \
       icrafttcirclet.bgf 

!include $(RESOURCEDIR)\copy.mak

{$(SOURCEDIR)}.bbg.bgf:
   $(MAKEBGF) -o $(OUTDIR)\$*.bgf @$*.bbg

clean:
