def render_top():
    import os
    os.system("clear")

    BLUE = "\033[38;2;23;147;209m"
    WHITE = "\033[1;37m"
    GRAY = "\033[90m"
    RESET = "\033[0m"

    panel_width = 120
    left_width = 40

    arch = [
        "                  -`",
        "                 .o+`",
        "                `ooo/",
        "               `+oooo:",
        "              `+oooooo:",
        "              -+oooooo+:",
        "            `/:-:++oooo+:",
        "           `/++++/+++++++:",
        "          `/++++++++++++++:",
        "         `/+++ooooooooooooo/`",
        "        ./ooosssso++osssssso+`",
        "       .oossssso-````/ossssss+`",
        "      -osssssso.      :ssssssso.",
        "     :osssssss/        osssso+++.",
        "    /ossssssss/        +ssssooo/-",
        "  `/ossssso+/:-        -:/+osssso+-",
        " `+sso+:-`                 `.-/+oso:",
        "`++:.                           `-/+/",
        ".`                                 `/",
    ]

    # 🔥 banner ajustado manualmente (sem centralização automática)
    carbonara = [
        "",
        "",
        "        ██████╗  █████╗  ██████╗  ██████╗  ██████╗   ███╗   ██╗",
        "       ██╔════╝ ██╔══██╗ ██╔══██╗ ██╔══██╗ ██╔═══██╗ ████╗  ██║",
        "       ██║      ███████║ ██████╔╝ ██████╔╝ ██║   ██║ ██╔██╗ ██║",
        "       ██║      ██╔══██║ ██╔══██╗ ██╔══██╗ ██║   ██║ ██║╚██╗██║",
        "       ╚██████╗ ██║  ██║ ██║  ██║ ██████╔╝ ╚██████╔╝ ██║ ╚████║",
        "        ╚═════╝ ╚═╝  ╚═╝ ╚═╝  ╚═╝ ╚═════╝   ╚═════╝  ╚═╝  ╚═══╝",
    ]

    max_lines = max(len(arch), len(carbonara))
    arch += [""] * (max_lines - len(arch))
    carbonara += [""] * (max_lines - len(carbonara))

    print(f"{BLUE}┌" + "─" * (panel_width - 2) + f"┐{RESET}")

    # padding topo
    print(f"{BLUE}│{' ' * (panel_width - 2)}│{RESET}")

    for a, c in zip(arch, carbonara):
        left = a.ljust(left_width)

        right_space = panel_width - left_width - 3

        # 👇 NÃO centraliza, só respeita o deslocamento manual
        right = c.ljust(right_space)

        print(
            f"{BLUE}│{RESET}"
            f"{BLUE}{left}{RESET}"
            f"{BLUE}│{RESET}"
            f"{WHITE}{right}{RESET}"
            f"{BLUE}│{RESET}"
        )

    # espaço antes da assinatura
    print(f"{BLUE}│{' ' * (panel_width - 2)}│{RESET}")

    content_width = panel_width - left_width - 3

    print(
        f"{BLUE}│{' ' * left_width}│"
        f"{WHITE}{' ' * 12 + 'Carbonara CLI'}{RESET}"
        f"{' ' * (content_width - 12 - len('Carbonara CLI'))}{BLUE}│{RESET}"
    )

    print(
        f"{BLUE}│{' ' * left_width}│"
        f"{GRAY}{' ' * 10 + 'Apollo Alves • Arch Linux'}{RESET}"
        f"{' ' * (content_width - 10 - len('Apollo Alves • Arch Linux'))}{BLUE}│{RESET}"
    )

    print(f"{BLUE}└" + "─" * (panel_width - 2) + f"┘{RESET}")
