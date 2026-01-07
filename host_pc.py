from debug.soft_break import bp

g_x = 10

def main():
    l_var = 15500
    l_l = [10, 20, 30]
    l_d = {"a": 10, "b": 20}
    s_s = "hello world"

    bp("main tag",
       locals_map=locals(),
       globals_map=globals(),
       with_log=True,
       state="aaa",
       mtu=11,
       rx_len=22)


if __name__ == '__main__':
    main()
