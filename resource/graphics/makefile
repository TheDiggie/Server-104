# makefile for object bitmaps

TOPDIR=..\..
!include $(TOPDIR)\common.mak

SOURCEDIR = $(TOPDIR)\resource\graphics
OUTDIR = $(TOPDIR)\resource\graphics

.SUFFIXES: .bbg

DIRS = daenks keen mark diggie delerium gar lod arantis morbus tyras cyrus patrick

BGFS = \
	$(OUTDIR)\arrowfir.bgf \
	$(OUTDIR)\arrowsil.bgf \
	$(OUTDIR)\arrowner.bgf \
	$(OUTDIR)\arrowice.bgf \
	$(OUTDIR)\mystswd.bgf \
	$(OUTDIR)\mystwdov.bgf \
	$(OUTDIR)\ring3.bgf \
	$(OUTDIR)\tikitrib.bgf \
	$(OUTDIR)\povmystsw.bgf

all:
	@-for %i in ($(DIRS)) do \
		@if EXIST %i ( cd %i & \
	 	$(MAKE) /$(MAKEFLAGS) $(COMMAND) &\
		cd .. )

clean:
	@-for %i in ($(DIRS)) do \
		@echo Making clean in %i & \
		@if EXIST %i ( cd %i & \
	 	$(MAKE) /$(MAKEFLAGS) clean &\
		cd .. )

{$(SOURCEDIR)}.bbg.bgf:
	$(MAKEBGF) -o $@ @$<

