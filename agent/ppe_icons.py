"""Simple labelled PPE illustrations, distinct from GHS hazard pictograms."""
from pathlib import Path
from PIL import Image, ImageDraw


def ppe_icon(kind: str, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"ppe-{kind}.png"
    image = Image.new("RGB", (240, 240), "white")
    d = ImageDraw.Draw(image)
    d.ellipse((8, 8, 232, 232), fill="#1766A3")
    if kind == "gloves":
        d.polygon([(88,188),(65,135),(48,118),(53,102),(68,103),(83,118),
                   (80,64),(90,58),(101,66),(106,111),(106,49),(118,45),
                   (128,52),(129,110),(140,57),(153,59),(157,70),(149,119),
                   (167,83),(180,87),(183,99),(164,158),(151,189)], fill="white")
    elif kind == "eyes":
        d.rounded_rectangle((44,88,108,142),radius=14,outline="white",width=9)
        d.rounded_rectangle((132,88,196,142),radius=14,outline="white",width=9)
        d.arc((101,99,139,125),180,360,fill="white",width=8)
        d.line((44,103,28,75),fill="white",width=8)
        d.line((196,103,212,75),fill="white",width=8)
    elif kind == "clothing":
        d.polygon([(85,54),(54,72),(31,139),(60,152),(76,111),(73,196),
                   (167,196),(164,111),(180,152),(209,139),(186,72),(155,54),
                   (120,80)], fill="white")
        d.line((120,81,120,190),fill="#1766A3",width=5)
        d.line((85,54,99,110,120,80,141,110,155,54),fill="#1766A3",width=4)
    elif kind == "rpe":
        d.arc((65,35,175,172),180,360,fill="white",width=7)
        d.polygon([(72,112),(120,92),(168,112),(158,159),(120,178),(82,159)],fill="white")
        d.line((72,115,48,90,46,128,82,152),fill="white",width=6)
        d.line((168,115,192,90,194,128,158,152),fill="white",width=6)
        d.ellipse((105,124,135,154),outline="#1766A3",width=5)
    elif kind == "face":
        d.arc((62,38,178,204),180,360,fill="white",width=9)
        d.rounded_rectangle((60,75,180,185),radius=22,outline="white",width=9)
        d.line((83,91,83,149),fill="white",width=5)
    elif kind == "footwear":
        d.polygon([(67,60),(131,60),(131,128),(177,150),
                   (191,170),(190,184),(58,184),(58,153),(67,134)],fill="white")
        d.line((59,171,189,171),fill="#1766A3",width=5)
    image.save(path)
    return path
