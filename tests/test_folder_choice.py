from run import pick_folder


def test_real_folder_is_used_when_it_exists(tmp_path):
    real, test = tmp_path / "real", tmp_path / "test"
    real.mkdir()
    assert pick_folder([], real_dir=real, test_dir=test) == real


def test_test_argument_uses_test_folder(tmp_path):
    real, test = tmp_path / "real", tmp_path / "test"
    real.mkdir()
    assert pick_folder(["test"], real_dir=real, test_dir=test) == test


def test_falls_back_to_test_folder_when_no_real_folder(tmp_path):
    assert pick_folder([], real_dir=tmp_path / "nope", test_dir=tmp_path / "test") == tmp_path / "test"
