import lw.viz.theme as theme


def test_package_imports():
    import lw.build.parse_lowlevel  # noqa: F401
    import lw.models.its  # noqa: F401


def test_palette_fixed_order_and_unique():
    assert len(theme.SERIES) == 8
    assert len(set(theme.SERIES)) == 8
    assert theme.SERIES[0] == "#2a78d6"


def test_save_fig_writes_png(tmp_path, monkeypatch):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    monkeypatch.setattr(theme, "FIG_DIR", tmp_path)
    theme.apply()
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    path = theme.save_fig(fig, "t", n=10)
    assert path.exists() and path.stat().st_size > 0
