from debug.soft_break import bp
import time

def main():
    x = 10
    y = "hello"
    z = [1, 2, 3]
    
    print("Before bp")
    bp("test", x=x, y=y, z=z, locals_map=locals())
    print("After bp")

if __name__ == "__main__":
    main()
