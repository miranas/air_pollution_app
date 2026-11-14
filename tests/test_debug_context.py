import contextlib

@contextlib.contextmanager
def moj_manager():
    print("1. ENTER - zdaj sem notri")
    yield "KOŠARICA"
    print("2. EXIT -zdaj sem zunaj")

print("O - pred with blokom")

with moj_manager()as x:
    print(f"2. V with bloku sem dobil {x}")

