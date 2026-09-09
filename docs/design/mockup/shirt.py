"""Flat-lay t-shirt mockup geometry.

A drawn garment, not a photograph. Its job is to give the Phase 2 directions a
real garment silhouette and a real 4:5 crop to lay out against, instead of a grey
box. Proportions are an oversize/boxy graphic tee (§7 `fit`), which is what
GRAPHIX actually sells. Every one of these is replaced by real photography.
"""

# 1000 x 1000 viewBox, symmetric about x = 500.
SHIRT_PATH = (
    "M 400,116 "
    "C 400,88 442,72 500,72 C 558,72 600,88 600,116 "        # collar
    "C 664,124 712,138 752,158 "                              # right shoulder
    "C 830,196 890,244 928,296 "                              # right sleeve outer
    "C 940,312 938,326 922,338 "
    "L 838,402 C 822,414 806,410 798,394 "                    # right sleeve hem
    "L 762,322 C 754,306 744,310 744,330 "                    # armpit
    "L 744,872 C 744,898 728,912 700,912 "                    # right side + hem
    "L 300,912 C 272,912 256,898 256,872 "
    "L 256,330 C 256,310 246,306 238,322 "                    # left side up
    "L 202,394 C 194,410 178,414 162,402 "
    "L 78,338 C 62,326 60,312 72,296 "                        # left sleeve
    "C 110,244 170,196 248,158 "
    "C 288,138 336,124 400,116 Z"
)

# Ribbed collar, drawn as a stroke so it reads at small sizes.
COLLAR_PATH = (
    "M 400,116 C 400,88 442,72 500,72 C 558,72 600,88 600,116 "
    "C 600,160 556,186 500,186 C 444,186 400,160 400,116 Z"
)

# Where a chest print sits: centre x, top y, max width, max height.
PRINT_BOX = (500, 300, 400, 400)
