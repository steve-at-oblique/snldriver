"""Level-2 paths, directory channels, conversion, metadata and confinement."""
import struct
import unittest
from pathlib import Path
from unittest.mock import patch
from tests import test_snl_serial as fixtures
snl = fixtures.snl


class DirectoryTests(unittest.TestCase):
    setUp = fixtures.SerialTests.setUp
    tearDown = fixtures.SerialTests.tearDown
    request = fixtures.SerialTests.request
    open = fixtures.SerialTests.open
    write = fixtures.SerialTests.write
    read = fixtures.SerialTests.read

    def mkdir(self, key=0):
        return self.request(b"\x20" + struct.pack(">I", key))

    def close(self):
        self.assertEqual(self.request(b"\x04"), b"\x00")

    def records(self, name=b""):
        result = self.open(name, mode=4)
        self.assertEqual(result[0], 0)
        size = int.from_bytes(result[1:], "big")
        data = bytearray()
        for offset in range(0, size, 512):
            data.extend(self.read(offset, min(512, size-offset))[3:])
        self.close()
        return [bytes(data[i:i+64]) for i in range(0, size, 64)]

    def names(self, records):
        return [r[16:16+int.from_bytes(r[14:16], "big")] for r in records]

    def test_existing_nested_directories_case_and_literal_underscores(self):
        (self.root / "Games" / "Board_Games").mkdir(parents=True)
        (self.root / "Games" / "Board_Games" / "Chess_bas").write_bytes(b"game")
        self.assertEqual(self.open(b"games_board_games_chess_BAS", mode=1), b"\x00\x00\x00\x00\x04")
        self.assertEqual(self.session.name, b"Games_Board_Games_Chess_bas")
        self.close()
        root = self.records()
        self.assertEqual(self.names(root), [b"Games"])
        self.assertEqual(root[0][5], 255)
        sub = self.records(b"GAMES_")
        self.assertEqual(self.names(sub), [b"Games_Board_Games"])
        self.assertEqual(sub[0][5], 255)
        self.assertEqual(self.names(self.records(b"games_board_games_ch")),
                         [b"Games_Board_Games_Chess_bas"])

    def test_create_save_header_rename_move_truncate_delete_in_subdirectories(self):
        (self.root / "one").mkdir()
        (self.root / "two").mkdir()
        self.open(b"one_file_bas")
        self.write(0, b"abcdef")
        self.session.file_date(1700000000, 0)
        self.session.file_version(42)
        self.assertEqual(self.session.path, self.root.resolve() / "one/file_bas")
        name = b"snl1_two_NEW_bas"
        self.assertEqual(self.request(bytes((0x1E, len(name))) + name), b"\x00")
        self.assertTrue((self.root / "two/.snl_headers/NEW_bas.json").exists())
        self.assertFalse((self.root / "one/.snl_headers/file_bas.json").exists())
        self.assertEqual(self.request(b"\x1f\x00\x00\x00\x03"), b"\x00")
        self.close()
        self.open(b"TWO_new_bas", mode=1)
        self.assertEqual(self.session.file_size(), 3)
        self.assertEqual(self.session.file_version(0xFFFFFFFF), 42)
        self.assertEqual(self.session.file_date(0xFFFFFFFF, 0), 1700000000)
        self.close()
        self.assertEqual(self.open(b"two_new_bas", mode=255), b"\x00")
        self.assertFalse((self.root / "two/NEW_bas").exists())
        self.assertEqual(self.open(b"two_", mode=255), b"\x00")
        self.assertFalse((self.root / "two").exists())

    def test_convert_empty_file_and_reopen_as_directory_channel(self):
        self.open(b"chess_")
        self.assertEqual(self.mkdir(), b"\x00" + bytes(4))
        self.assertEqual(self.session.mode, 4)
        self.assertEqual(self.session.read_header()[5], 255)
        self.assertTrue((self.root / "chess").is_dir())
        self.assertEqual(self.write(0, b"no"), snl.status(snl.RO) + bytes(2))
        self.close()
        self.assertEqual(self.names(self.records()), [b"chess"])
        self.open(b"chess_game_bas")
        self.write(0, b"new game")
        self.close()
        self.assertEqual((self.root / "chess/game_bas").read_bytes(), b"new game")
        self.assertEqual(self.names(self.records(b"chess_")), [b"chess_game_bas"])

    def test_make_directory_adopts_prefix_files_and_sidecars(self):
        self.open(b"games_chess_bas")
        self.write(0, b"chess")
        self.session.file_version(42)
        self.close()
        (self.root / "games_go_bas").write_bytes(b"go")
        self.open(b"games")
        self.assertEqual(self.mkdir(), b"\x00" + struct.pack(">I", 128))
        self.close()
        self.assertFalse((self.root / "games_chess_bas").exists())
        self.assertTrue((self.root / "games/.snl_headers/chess_bas.json").exists())
        self.open(b"games_chess_bas", mode=1)
        self.assertEqual(self.session.file_version(0xFFFFFFFF), 42)
        self.close()
        self.assertEqual(self.names(self.records(b"games_")),
                         [b"games_chess_bas", b"games_go_bas"])

    def test_make_directory_invalid_key_nonempty_readonly_and_existing(self):
        self.open(b"nonempty")
        self.write(0, b"keep")
        self.assertEqual(self.mkdir(), snl.status(snl.BP))
        self.close()
        self.open(b"empty")
        self.assertEqual(self.mkdir(1), snl.status(snl.BP))
        self.close()
        self.open(b"empty", mode=1)
        self.assertEqual(self.mkdir(), snl.status(snl.RO))
        self.close()
        (self.root / "existing").mkdir()
        self.assertEqual(self.open(b"existing", mode=2), snl.status(snl.EX))
        self.assertEqual(self.open(b"existing", mode=3), snl.status(snl.EX))

    def test_delete_nonempty_directory_preserves_files(self):
        (self.root / "folder").mkdir()
        (self.root / "folder/keep").write_bytes(b"keep")
        self.assertEqual(self.open(b"folder_", mode=255), snl.status(snl.IU))
        self.assertEqual((self.root / "folder/keep").read_bytes(), b"keep")

    def test_nested_symlinks_reserved_metadata_and_traversal_rejected(self):
        (self.root / "folder").mkdir()
        (self.root / "folder/link").symlink_to(self.root)
        for name in (b"folder_.snl_headers", b"folder_../x", b"folder_link"):
            self.assertEqual(self.open(name, mode=1), snl.status(snl.BN), name)
        self.assertEqual(self.names(self.records(b"folder_")), [])

    def test_exact_flat_names_win_and_shadowed_nested_listing_is_rejected(self):
        (self.root / "a").mkdir()
        (self.root / "a/b").write_bytes(b"nested")
        (self.root / "a_b").write_bytes(b"flat")
        self.open(b"a_b", mode=1)
        self.assertEqual(self.session.read(0, 4), b"flat")
        self.close()
        self.assertEqual(self.open(b"a_", mode=4), snl.status(snl.BN))

    def test_failed_adoption_rolls_back_files_and_empty_placeholder(self):
        self.open(b"group_item")
        self.write(0, b"item")
        self.close()
        self.open(b"group")
        original = Path.rename
        def fail_meta(path, target):
            if path.name == "group_item.json":
                raise PermissionError("injected metadata failure")
            return original(path, target)
        with patch.object(Path, "rename", fail_meta):
            self.assertEqual(self.mkdir(), snl.status(snl.RO))
        self.assertTrue((self.root / "group").is_file())
        self.assertEqual((self.root / "group_item").read_bytes(), b"item")
        self.assertTrue((self.root / ".snl_headers/group_item.json").exists())
        self.assertEqual(self.session.mode, 2)
        self.assertEqual(self.mkdir(), b"\x00" + struct.pack(">I", 64))

    def test_36_byte_limit_applies_to_complete_ql_path(self):
        (self.root / "folder").mkdir()
        self.assertEqual(self.open(b"folder_" + b"a" * 30), snl.status(snl.BN))
        self.assertEqual(self.open(b"folder_" + b"a" * 29), b"\x00" + bytes(4))
