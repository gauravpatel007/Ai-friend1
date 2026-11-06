import struct

def inspect_ico(path):
    with open(path, "rb") as f:
        data = f.read()
    reserved, type_, count = struct.unpack("<HHH", data[:6])
    print(f"File {path}: count={count}, type={type_}")
    for i in range(count):
        offset = 6 + i * 16
        w, h, colors, res, planes, bpp, size, img_offset = struct.unpack("<BBBBHHII", data[offset:offset+16])
        w = 256 if w == 0 else w
        h = 256 if h == 0 else h
        is_png = data[img_offset:img_offset+8] == b"\x89PNG\r\n\x1a\n"
        print(f"  Frame {i}: {w}x{h}, bpp={bpp}, size={size}, offset={img_offset}, is_png={is_png}")

inspect_ico("assets/icons/app_icon.ico")
