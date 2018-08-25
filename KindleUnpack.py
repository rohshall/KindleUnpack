import sys
import os
import lib.kindleunpack as kindleunpack
   

def main():
    mobipath = "/home/salil/Documents/Books/mobis"
    outdir = "/home/salil/Documents/Books"
    for filename in os.listdir(mobipath):
        kindleunpack.unpackBook(mobipath + "/" + filename, outdir)
    return 0

if __name__ == "__main__":
    sys.exit(main())
