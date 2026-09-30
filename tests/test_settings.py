from run import pick_folder
from fintrack.settings import saved_folder, save_folder


def test_save_and_read_back(tmp_path):
    f, folder = tmp_path / "saved.txt", tmp_path / "my statements"
    folder.mkdir()
    save_folder(folder, saved_file=f)
    assert saved_folder(saved_file=f) == folder
    other = tmp_path / "other"
    other.mkdir()
    save_folder(other, saved_file=f)                 # replaces
    assert saved_folder(saved_file=f) == other


def test_missing_empty_or_gone_gives_none(tmp_path):
    f = tmp_path / "saved.txt"
    assert saved_folder(saved_file=f) is None
    f.write_text("")
    assert saved_folder(saved_file=f) is None
    save_folder(tmp_path / "does not exist", saved_file=f)
    assert saved_folder(saved_file=f) is None


def test_pick_folder_priority(tmp_path):
    real, inner, mine = tmp_path / "real", tmp_path / "inner", tmp_path / "mine"
    for d in (real, inner, mine):
        d.mkdir()
    f = tmp_path / "saved.txt"
    save_folder(mine, saved_file=f)
    assert pick_folder(["test"], real_dir=real, test_dir=inner, saved_file=f) == inner   # test wins
    assert pick_folder([], real_dir=real, test_dir=inner, saved_file=f) == mine          # then the saved one
    f.unlink()
    assert pick_folder([], real_dir=real, test_dir=inner, saved_file=f) == real          # then the real sibling
    assert pick_folder([], real_dir=tmp_path / "nope", test_dir=inner, saved_file=f) == inner
