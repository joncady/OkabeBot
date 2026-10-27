"""Small-screen set dressing; geometry only, no I/O or world ownership logic."""

SETS = ("pixel-lab", "maid-cafe", "pip-workshop", "rooftop-garden", "green-hill", "star-light")


def dressing(selected):
    out = []

    def rect(x, y, w, h, color):
        out.append(("rectangle", (x, y, x + w, y + h), color, 1))

    cafe, roof, night = (
        selected == "maid-cafe",
        selected == "rooftop-garden",
        selected == "star-light",
    )
    base = "#805440" if cafe else "#587568" if roof else "#38365b" if night else "#466570"
    rect(85, 294, 310, 20, base)
    rect(85, 290, 310, 5, "#cfaa88" if cafe else "#84b494")
    if cafe:
        rect(96, 269, 20, 20, "#ece0be")
        rect(116, 273, 6, 10, "#ece0be")
        rect(358, 261, 28, 29, "#354f48")
        rect(362, 266, 20, 3, "#ded6b0")
    elif roof or selected == "green-hill":
        for x in (105, 375):
            rect(x, 265, 4, 25, "#64a86a")
            rect(x - 6, 263, 16, 7, "#e4c56e")
    elif night:
        for x in (104, 374):
            rect(x, 255, 5, 35, "#8d91b1")
            rect(x - 5, 251, 15, 8, "#e7ca89")
    else:
        rect(96, 267, 25, 22, "#76aaa9")
        rect(100, 271, 17, 11, "#213f4d")
        rect(365, 264, 7, 26, "#91c0c4")
        rect(357, 278, 22, 12, "#69a6a2")
    return out
