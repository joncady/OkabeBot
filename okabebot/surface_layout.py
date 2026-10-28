"""Discrete screen arrangement shared by adapters, dashboard and movement."""

DIRECTIONS = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}
LIMIT = 10


def nearest_free(point, occupied):
    candidates = (
        (x, y)
        for x in range(-LIMIT, LIMIT + 1)
        for y in range(-LIMIT, LIMIT + 1)
        if (x, y) not in occupied
    )
    return min(
        candidates,
        key=lambda p: (
            abs(p[0] - point[0]) + abs(p[1] - point[1]),
            abs(p[1]),
            p[1],
            abs(p[0]),
            p[0],
        ),
    )


def positions(places, saved):
    """Resolve legacy overlaps without mutating state; reserve pending screens too."""
    result, occupied = {}, set()
    for i, place in enumerate(places):
        default = (
            (0, 0)
            if place["adapter"] == "pi"
            else (-1, 0)
            if place["adapter"] == "cast"
            else (i, 0)
        )
        point = tuple(max(-LIMIT, min(LIMIT, round(v))) for v in saved.get(place["id"], default))
        if point in occupied:
            point = nearest_free(point, occupied)
        result[place["id"]] = list(point)
        occupied.add(point)
    return result


def validate(point):
    if (
        not isinstance(point, list)
        or len(point) != 2
        or any(type(v) is not int or abs(v) > LIMIT for v in point)
    ):
        raise ValueError("Screen positions must be two integer grid coordinates within -10..10")
    return point


def direction(origin, target):
    dx, dy = target[0] - origin[0], target[1] - origin[1]
    if dx == dy == 0:
        raise ValueError("Choose two different screen positions")
    return ("left" if dx < 0 else "right") if abs(dx) > abs(dy) else ("up" if dy < 0 else "down")
