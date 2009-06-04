from __future__ import with_statement
__license__   = 'GPL v3'
__copyright__ = '2008, Kovid Goyal <kovid at kovidgoyal.net>'
'''Read meta information from PDF files'''

import sys, os, cStringIO
from threading import Thread

from calibre import StreamReadWrapper
from calibre.ptempfile import TemporaryDirectory
try:
    from calibre.utils.PythonMagickWand import \
        NewMagickWand, MagickReadImage, MagickSetImageFormat, \
        MagickWriteImage, ImageMagick
    _imagemagick_loaded = True
except:
    _imagemagick_loaded = False
from calibre.ebooks.metadata import MetaInformation, authors_to_string
from calibre.utils.pdftk import set_metadata as pdftk_set_metadata
from calibre.utils.podofo import get_metadata as podofo_get_metadata, \
    set_metadata as podofo_set_metadata, Unavailable, write_first_page, \
    get_metadata_quick

def get_quick_metadata(stream):
    raw = stream.read()
    mi = get_metadata_quick(raw)
    if mi.title == '_':
        mi.title = getattr(stream, 'name', _('Unknown'))
        mi.title = mi.title.rpartition('.')[0]
    return mi


def get_metadata(stream, extract_cover=True):
    try:
        mi = podofo_get_metadata(stream)
    except Unavailable:
        mi = get_metadata_pypdf(stream)
    stream.seek(0)

    if extract_cover and _imagemagick_loaded:
        try:
            cdata = get_cover(stream)
            if cdata is not None:
                mi.cover_data = ('jpg', cdata)
        except:
            import traceback
            traceback.print_exc()
    return mi


def set_metadata(stream, mi):
    stream.seek(0)
    try:
        return podofo_set_metadata(stream, mi)
    except Unavailable:
        pass
    try:
        return pdftk_set_metadata(stream, mi)
    except:
        pass
    set_metadata_pypdf(stream, mi)


def get_metadata_pypdf(stream):
    """ Return metadata as a L{MetaInfo} object """
    from pyPdf import PdfFileReader
    mi = MetaInformation(_('Unknown'), [_('Unknown')])
    try:
        with StreamReadWrapper(stream) as stream:
            info = PdfFileReader(stream).getDocumentInfo()
            if info.title:
                mi.title = info.title
            if info.author:
                src = info.author.split('&')
                authors = []
                for au in src:
                    authors += au.split(',')
                mi.authors = authors
                mi.author = info.author
            if info.subject:
                mi.category = info.subject
    except Exception, err:
        msg = u'Couldn\'t read metadata from pdf: %s with error %s'%(mi.title, unicode(err))
        print >>sys.stderr, msg.encode('utf8')
    return mi

class MetadataWriter(Thread):

    def __init__(self, out_pdf, buf):
        self.out_pdf = out_pdf
        self.buf = buf
        Thread.__init__(self)
        self.daemon = True

    def run(self):
        try:
            self.out_pdf.write(self.buf)
        except RuntimeError:
            pass

def set_metadata_pypdf(stream, mi):
    # Use a StringIO object for the pdf because we will want to over
    # write it later and if we are working on the stream directly it
    # could cause some issues.

    from pyPdf import PdfFileReader, PdfFileWriter
    raw = cStringIO.StringIO(stream.read())
    orig_pdf = PdfFileReader(raw)
    title = mi.title if mi.title else orig_pdf.documentInfo.title
    author = authors_to_string(mi.authors) if mi.authors else orig_pdf.documentInfo.author
    out_pdf = PdfFileWriter(title=title, author=author)
    out_str = cStringIO.StringIO()
    writer = MetadataWriter(out_pdf, out_str)
    for page in orig_pdf.pages:
        out_pdf.addPage(page)
    writer.start()
    writer.join(10) # Wait 10 secs for writing to complete
    out_pdf.killed = True
    writer.join()
    if out_pdf.killed:
        print 'Failed to set metadata: took too long'
        return

    stream.seek(0)
    stream.truncate()
    out_str.seek(0)
    stream.write(out_str.read())
    stream.seek(0)

def get_cover(stream):
    stream.seek(0)
    with TemporaryDirectory('_pdfmeta') as tdir:
        cover_path = os.path.join(tdir, 'cover.pdf')
        write_first_page(stream, cover_path)
        with ImageMagick():
            wand = NewMagickWand()
            MagickReadImage(wand, cover_path)
            MagickSetImageFormat(wand, 'JPEG')
            MagickWriteImage(wand, '%s.jpg' % cover_path)
        return open('%s.jpg' % cover_path, 'rb').read()



