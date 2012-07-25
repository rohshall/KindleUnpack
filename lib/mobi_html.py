#!/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai


DEBUG=False

import sys, os
import array, struct, re

from mobi_utils import getLanguage, toHex, fromBase32, toBase32


class HTMLProcessor:
    def __init__(self, files, metadata, imgnames):
        self.files = files
        self.metadata = metadata
        self.imgnames = imgnames
        # for original style mobis, default to including all image files in the opf manifest
        self.used = {}
        for name in imgnames:
            self.used[name] = 'used'

    def findAnchors(self, rawtext, indx_data, positionMap):
        # process the raw text
        # find anchors...
        print "Find link anchors"
        link_pattern = re.compile(r'''<[^<>]+filepos=['"]{0,1}(\d+)[^<>]*>''', re.IGNORECASE)
        # TEST NCX: merge in filepos from indx
        pos_links = [int(m.group(1)) for m in link_pattern.finditer(rawtext)]
        if indx_data:
            pos_indx = [e['pos'] for e in indx_data if e['pos']>0]
            pos_links = list(set(pos_links + pos_indx))

        for position in pos_links:
            if position in positionMap:
                positionMap[position] = positionMap[position] + '<a id="filepos%d" />' % position
            else:
                positionMap[position] = '<a id="filepos%d" />' % position

        # apply dictionary metadata and anchors
        print "Insert data into html"
        pos = 0
        lastPos = len(rawtext)
        dataList = []
        for end in sorted(positionMap.keys()):
            if end == 0 or end > lastPos:
                continue # something's up - can't put a tag in outside <html>...</html>
            dataList.append(rawtext[pos:end])
            dataList.append(positionMap[end])
            pos = end
        dataList.append(rawtext[pos:])
        srctext = "".join(dataList)
        rawtext = None
        datalist = None
        self.srctext = srctext
        self.indx_data = indx_data
        return srctext

    def insertHREFS(self):
        srctext = self.srctext
        imgnames = self.imgnames
        files = self.files
        metadata = self.metadata

        # put in the hrefs
        print "Insert hrefs into html"
        # There doesn't seem to be a standard, so search as best as we can
        
        link_pattern = re.compile(r'''<a([^>]*?)filepos=['"]{0,1}0*(\d+)['"]{0,1}([^>]*?)>''', re.IGNORECASE)
        srctext = link_pattern.sub(r'''<a\1href="#filepos\2"\3>''', srctext)

        # remove empty anchors
        print "Remove empty anchors from html"
        srctext = re.sub(r"<a/>",r"", srctext)
        srctext = re.sub(r"<a ?></a>",r"", srctext)
        
        # convert image references
        print "Insert image references into html"
        # split string into image tag pieces and other pieces
        image_pattern = re.compile(r'''(<img.*?>)''', re.IGNORECASE)
        image_index_pattern = re.compile(r'''recindex=['"]{0,1}([0-9]+)['"]{0,1}''', re.IGNORECASE)
        srcpieces = image_pattern.split(srctext)
        srctext = self.srctext = None

        # all odd pieces are image tags (nulls string on even pieces if no space between them in srctext)
        for i in range(1, len(srcpieces), 2):
            tag = srcpieces[i]
            for m in image_index_pattern.finditer(tag):
                imageNumber = int(m.group(1))
                imageName = imgnames[imageNumber-1]
                if imageName is None:
                    print "Error: Referenced image %s was not recognized as a valid image" % imageNumber
                else:
                    replacement = 'src="Images/' + imageName + '"'
                    tag = image_index_pattern.sub(replacement, tag, 1)
            srcpieces[i] = tag
        srctext = "".join(srcpieces)

        # add in character set meta into the html header if needed
        if 'Codec' in metadata:
            srctext = srctext[0:12]+'<meta http-equiv="content-type" content="text/html; charset='+metadata.get('Codec')[0]+'" />'+srctext[12:]
        return srctext, self.used




class XHTMLK8Processor:
    def __init__(self, imgnames, k8proc):
        self.imgnames = imgnames
        self.k8proc = k8proc
        self.used = {}

    def buildXHTML(self):

        # first need to update all links that are internal which
        # are based on positions within the xhtml files **BEFORE**
        # cutting and pasting any pieces into the xhtml text files

        #   kindle:pos:fid:XXXX:off:YYYYYYYYYY  (used for internal link within xhtml)
        #       XXXX is the offset in records into divtbl
        #       YYYYYYYYYYYY is a base32 number you add to the divtbl insertpos to get final position


        # pos:fid pattern
        posfid_pattern = re.compile(r'''(<a.*?href=.*?>)''', re.IGNORECASE)
        posfid_index_pattern = re.compile(r'''['"]kindle:pos:fid:([0-9|A-V]+):off:([0-9|A-V]+).*?["']''')

        parts = []
        print "Building proper xhtml for each file"
        for i in xrange(self.k8proc.getNumberOfParts()):
            part = self.k8proc.getPart(i)
            [partnum, dir, filename, beg, end, aidtext] = self.k8proc.getPartInfo(i)

            # internal links
            srcpieces = posfid_pattern.split(part)
            for j in range(1, len(srcpieces),2):
                tag = srcpieces[j]
                if tag.startswith('<'):
                    for m in posfid_index_pattern.finditer(tag):
                        posfid = m.group(1)
                        offset = m.group(2)
                        filename, idtag = self.k8proc.getIDTagByPosFid(posfid, offset)
                        if idtag == '':
                            replacement= '"' + filename + '"'
                        else:
                            replacement = '"' + filename + '#' + idtag + '"'
                        tag = posfid_index_pattern.sub(replacement, tag, 1)
                    srcpieces[j] = tag
            part = "".join(srcpieces)
            parts.append(part)


        # we are free to cut and paste as we see fit
        # we can safely remove all of the Kindlegen generated aid tags
        find_tag_with_aid_pattern = re.compile(r'''(<[^>]*\said\s*=[^>]*>)''', re.IGNORECASE)
        within_tag_aid_position_pattern = re.compile(r'''\said\s*=['"][^'"]*['"]''')
        for i in xrange(len(parts)):
            part = parts[i]
            srcpieces = find_tag_with_aid_pattern.split(part)
            for j in range(len(srcpieces)):
                tag = srcpieces[j]
                if tag.startswith('<'):
                    for m in within_tag_aid_position_pattern.finditer(tag):
                        replacement = ''
                        tag = within_tag_aid_position_pattern.sub(replacement, tag, 1)
                    srcpieces[j] = tag
            part = "".join(srcpieces)
            parts[i] = part

        # we can safely remove all of the Kindlegen generated data-AmznPageBreak tags
        find_tag_with_AmznPageBreak_pattern = re.compile(r'''(<[^>]*\sdata-AmznPageBreak=[^>]*>)''', re.IGNORECASE)
        within_tag_AmznPageBreak_position_pattern = re.compile(r'''\sdata-AmznPageBreak=['"][^'"]*['"]''')
        for i in xrange(len(parts)):
            part = parts[i]
            srcpieces = find_tag_with_AmznPageBreak_pattern.split(part)
            for j in range(len(srcpieces)):
                tag = srcpieces[j]
                if tag.startswith('<'):
                    for m in within_tag_AmznPageBreak_position_pattern.finditer(tag):
                        replacement = ''
                        tag = within_tag_AmznPageBreak_position_pattern.sub(replacement, tag, 1)
                    srcpieces[j] = tag
            part = "".join(srcpieces)
            parts[i] = part


        # we have to handle substitutions for the flows  pieces first as they may
        # be inlined into the xhtml text
        #   kindle:embed:XXXX?mime=image/gif (png, jpeg, etc) (used for images)
        #   kindle:flow:XXXX?mime=YYYY/ZZZ (used for style sheets, svg images, etc)
        #   kindle:embed:XXXX   (used for fonts)

        flows = []
        flows.append(None)
        flowinfo = []
        flowinfo.append([None, None, None, None])

        # regular expression search patterns
        img_pattern = re.compile(r'''(<[img\s|image\s][^>]*>)''', re.IGNORECASE)
        img_index_pattern = re.compile(r'''[('"]kindle:embed:([0-9|A-V]+)[^'"]*['")]''', re.IGNORECASE)

        tag_pattern = re.compile(r'''(<[^>]*>)''')
        flow_pattern = re.compile(r'''['"]kindle:flow:([0-9|A-V]+)\?mime=([^'"]+)['"]''', re.IGNORECASE)

        url_pattern = re.compile(r'''(url\(.*?\))''', re.IGNORECASE)
        url_img_index_pattern = re.compile(r'''[('"]kindle:embed:([0-9|A-V]+)\?mime=image/[^\)]*["')]''', re.IGNORECASE)
        font_index_pattern = re.compile(r'''[('"]kindle:embed:([0-9|A-V]+)["')]''', re.IGNORECASE)
        url_css_index_pattern = re.compile(r'''kindle:flow:([0-9|A-V]+)\?mime=text/css[^\)]*''', re.IGNORECASE)

        for i in xrange(1, self.k8proc.getNumberOfFlows()):
            [type, format, dir, filename] = self.k8proc.getFlowInfo(i)
            flowpart = self.k8proc.getFlow(i)

            # links to raster image files from image tags
            # image_pattern
            srcpieces = img_pattern.split(flowpart)
            for j in range(1, len(srcpieces),2):
                tag = srcpieces[j]
                if tag.startswith('<im'):
                    for m in img_index_pattern.finditer(tag):
                        imageNumber = fromBase32(m.group(1))
                        imageName = self.imgnames[imageNumber-1]
                        if imageName != None:
                            replacement = '"../Images/' + imageName + '"'
                            self.used[imageName] = 'used'
                            tag = img_index_pattern.sub(replacement, tag, 1)
                        else:
                            print "Error: Referenced image %s was not recognized as a valid image in %s" % (imageNumber, tag)
                    srcpieces[j] = tag
            flowpart = "".join(srcpieces)

            # replacements inside css url():
            srcpieces = url_pattern.split(flowpart)
            for j in range(1, len(srcpieces),2):
                tag = srcpieces[j]

                #  process links to raster image files
                for m in url_img_index_pattern.finditer(tag):
                    imageNumber = fromBase32(m.group(1))
                    imageName = self.imgnames[imageNumber-1]
                    osep = m.group()[0]
                    csep = m.group()[-1]
                    if imageName != None:
                        replacement = '%s%s%s'%(osep, '../Images/' + imageName, csep)
                        self.used[imageName] = 'used'
                        tag = url_img_index_pattern.sub(replacement, tag, 1)
                    else:
                        print "Error: Referenced image %s was not recognized as a valid image in %s" % (imageNumber, tag)

                # process links to fonts
                for m in font_index_pattern.finditer(tag):
                    fontNumber = fromBase32(m.group(1))
                    fontName = self.imgnames[fontNumber-1]
                    osep = m.group()[0]
                    csep = m.group()[-1]
                    if fontName is None:
                        print "Error: Referenced font %s was not recognized as a valid font in %s" % (fontNumber, tag)
                    else:
                        replacement = '%s%s%s'%(osep, '../Fonts/' + fontName, csep)
                        tag = font_index_pattern.sub(replacement, tag, 1)
                        self.used[fontName] = 'used'


                # process links to other css pieces
                for m in url_css_index_pattern.finditer(tag):
                    num = fromBase32(m.group(1))
                    [typ, fmt, pdir, fnm] = self.k8proc.getFlowInfo(num)
                    replacement = '"../' + pdir + '/' + fnm + '"'
                    tag = url_css_index_pattern.sub(replacement, tag, 1)
                    self.used[fnm] = 'used'

                srcpieces[j] = tag
            flowpart = "".join(srcpieces)

            # store away in our own copy
            flows.append(flowpart)

            # I do no thtink this case exists and even if it does exist, it needs to be done in a separate
            # pass to prevent inlining a flow piece into another flow piece before the inserted one or the
            # target one has been fully processed

            # but keep it around if it ends up we do need it

            # # flow pattern not inside url()
            # srcpieces = tag_pattern.split(flowpart)
            # for j in range(1, len(srcpieces),2):
            #     tag = srcpieces[j]
            #     if tag.startswith('<'):
            #         for m in flow_pattern.finditer(tag):
            #             num = fromBase32(m.group(1))
            #             [typ, fmt, pdir, fnm] = self.k8proc.getFlowInfo(num)
            #             flowtext = self.k8proc.getFlow(num)
            #             if fmt == 'inline':
            #                 tag = flowtext
            #             else:
            #                 replacement = '"../' + pdir + '/' + fnm + '"'
            #                 tag = flow_pattern.sub(replacement, tag, 1)
            #                 self.used[fnm] = 'used'
            #         srcpieces[j] = tag
            # flowpart = "".join(srcpieces)

        # now handle the main text xhtml parts

        # Handle the flow items in the XHTML text pieces
        # kindle:flow:XXXX?mime=YYYY/ZZZ (used for style sheets, svg images, etc)
        tag_pattern = re.compile(r'''(<[^>]*>)''')
        flow_pattern = re.compile(r'''['"]kindle:flow:([0-9|A-V]+)\?mime=([^'"]+)['"]''', re.IGNORECASE)
        for i in xrange(len(parts)):
            part = parts[i]
            [partnum, dir, filename, beg, end, aidtext] = self.k8proc.partinfo[i]

            # flow pattern
            srcpieces = tag_pattern.split(part)
            for j in range(1, len(srcpieces),2):
                tag = srcpieces[j]
                if tag.startswith('<'):
                    for m in flow_pattern.finditer(tag):
                        num = fromBase32(m.group(1))
                        [typ, fmt, pdir, fnm] = self.k8proc.getFlowInfo(num)
                        flowpart = flows[num]
                        if fmt == 'inline':
                            tag = flowpart
                        else:
                            replacement = '"../' + pdir + '/' + fnm + '"'
                            tag = flow_pattern.sub(replacement, tag, 1)
                            self.used[fnm] = 'used'
                    srcpieces[j] = tag
            part = "".join(srcpieces)

            # store away modified version
            parts[i] = part

        # Handle any embedded raster images links in style= attributes urls
        style_pattern = re.compile(r'''(<[a-zA-Z0-9]+\s[^>]*style\s*=\s*[^>]*>)''', re.IGNORECASE)
        img_index_pattern = re.compile(r'''[('"]kindle:embed:([0-9|A-V]+)[^'"]*['")]''', re.IGNORECASE)

        for i in xrange(len(parts)):
            part = parts[i]
            [partnum, dir, filename, beg, end, aidtext] = self.k8proc.partinfo[i]

            # replace urls in style attributes
            srcpieces = style_pattern.split(part)
            for j in range(1, len(srcpieces),2):
                tag = srcpieces[j]
                if 'kindle:embed' in tag:
                    for m in img_index_pattern.finditer(tag):
                        imageNumber = fromBase32(m.group(1))
                        imageName = self.imgnames[imageNumber-1]
                        osep = m.group()[0]
                        csep = m.group()[-1]
                        if imageName != None:
                            replacement = '%s%s%s'%(osep, '../Images/' + imageName, csep)
                            self.used[imageName] = 'used'
                            tag = img_index_pattern.sub(replacement, tag, 1)
                        else:
                            print "Error: Referenced image %s in style url was not recognized in %s" % (imageNumber, tag)
                    srcpieces[j] = tag
            part = "".join(srcpieces)

            # store away modified version
            parts[i] = part

        # Handle any embedded raster images links in the xhtml text
        # kindle:embed:XXXX?mime=image/gif (png, jpeg, etc) (used for images)
        img_pattern = re.compile(r'''(<[img\s|image\s][^>]*>)''', re.IGNORECASE)
        img_index_pattern = re.compile(r'''['"]kindle:embed:([0-9|A-V]+)[^'"]*['"]''')

        for i in xrange(len(parts)):
            part = parts[i]
            [partnum, dir, filename, beg, end, aidtext] = self.k8proc.partinfo[i]

            # links to raster image files
            # image_pattern
            srcpieces = img_pattern.split(part)
            for j in range(1, len(srcpieces),2):
                tag = srcpieces[j]
                if tag.startswith('<im'):
                    for m in img_index_pattern.finditer(tag):
                        imageNumber = fromBase32(m.group(1))
                        imageName = self.imgnames[imageNumber-1]
                        if imageName != None:
                            replacement = '"../Images/' + imageName + '"'
                            self.used[imageName] = 'used'
                            tag = img_index_pattern.sub(replacement, tag, 1)
                        else:
                            print "Error: Referenced image %s was not recognized as a valid image in %s" % (imageNumber, tag)
                    srcpieces[j] = tag
            part = "".join(srcpieces)
            # store away modified version
            parts[i] = part


        # finally perform any general cleanups needed to make valid XHTML
        # these include:
        #   in svg tags replace "perserveaspectratio" attributes with "perserveAspectRatio"
        #   in svg tags replace "viewbox" attributes with "viewBox"
        #   in <li> remove value="XX" attributes since these are illegal
        tag_pattern = re.compile(r'''(<[^>]*>)''')
        li_value_pattern = re.compile(r'''\svalue\s*=\s*['"][^'"]*['"]''', re.IGNORECASE)

        for i in xrange(len(parts)):
            part = parts[i]
            [partnum, dir, filename, beg, end, aidtext] = self.k8proc.partinfo[i]

            # tag pattern
            srcpieces = tag_pattern.split(part)
            for j in range(1, len(srcpieces),2):
                tag = srcpieces[j]
                if tag.startswith('<svg') or tag.startswith('<SVG'):
                    tag = tag.replace('preserveaspectratio','preserveAspectRatio')
                    tag = tag.replace('viewbox','viewBox')
                elif tag.startswith('<li ') or tag.startswith('<LI '):
                    tagpieces = li_value_pattern.split(tag)
                    tag = "".join(tagpieces)
                srcpieces[j] = tag
            part = "".join(srcpieces)
            # store away modified version
            parts[i] = part

        self.k8proc.setFlows(flows)
        self.k8proc.setParts(parts)

        return self.used