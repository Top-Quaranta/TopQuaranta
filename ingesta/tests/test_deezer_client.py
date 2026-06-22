from datetime import date
from unittest.mock import patch

from ingesta.clients.deezer import (
    _normalize,
    get_album_tracks,
    get_artist_albums,
    search_artist,
)


class TestNormalize:
    def test_lowercase(self):
        assert _normalize("Zoo") == "zoo"

    def test_strip_accents(self):
        assert _normalize("La Fúmiga") == "la fumiga"

    def test_strip_accents_catalan(self):
        assert _normalize("Mandràgora") == "mandragora"

    def test_strip_whitespace(self):
        assert _normalize("  Zoo  ") == "zoo"

    def test_combined(self):
        assert _normalize(" OQUES GRASSES ") == "oques grasses"


class TestSearchArtist:
    @patch("ingesta.clients.deezer._get")
    def test_exact_match(self, mock_get):
        mock_get.return_value = {
            "data": [
                {"id": 98469, "name": "ZOO"},
                {"id": 9999, "name": "Zoomania"},
            ]
        }
        result = search_artist("Zoo")
        assert result == {"id": 98469, "name": "ZOO"}

    @patch("ingesta.clients.deezer._get")
    def test_accent_match(self, mock_get):
        mock_get.return_value = {
            "data": [
                {"id": 14102055, "name": "La Fúmiga"},
            ]
        }
        result = search_artist("La Fumiga")
        assert result == {"id": 14102055, "name": "La Fúmiga"}

    @patch("ingesta.clients.deezer._get")
    def test_containment_match(self, mock_get):
        mock_get.return_value = {
            "data": [
                {"id": 5541552, "name": "OQUES GRASSES"},
            ]
        }
        result = search_artist("Oques Grasses")
        assert result == {"id": 5541552, "name": "OQUES GRASSES"}

    @patch("ingesta.clients.deezer._get")
    def test_no_match_returns_none(self, mock_get):
        mock_get.return_value = {
            "data": [
                {"id": 11386020, "name": "Miura Jam"},
                {"id": 5203877, "name": "Mourn"},
            ]
        }
        result = search_artist("Miurn")
        assert result is None

    @patch("ingesta.clients.deezer._get")
    def test_empty_results(self, mock_get):
        mock_get.return_value = {"data": []}
        assert search_artist("NonexistentArtist") is None

    @patch("ingesta.clients.deezer._get")
    def test_api_error(self, mock_get):
        mock_get.return_value = None
        assert search_artist("Zoo") is None


class TestGetArtistAlbums:
    @patch("ingesta.clients.deezer._get")
    def test_returns_filtered_albums(self, mock_get):
        mock_get.return_value = {
            "data": [
                {
                    "id": 100,
                    "title": "New Album",
                    "release_date": "2026-01-15",
                    "cover_xl": "https://img.com/1.jpg",
                    "record_type": "album",
                },
                {
                    "id": 200,
                    "title": "Old Album",
                    "release_date": "2020-03-01",
                    "cover_xl": "https://img.com/2.jpg",
                    "record_type": "album",
                },
            ],
            "next": None,
        }

        albums = get_artist_albums(98469, min_date=date(2025, 4, 10))

        assert len(albums) == 1
        assert albums[0]["title"] == "New Album"
        assert albums[0]["release_date"] == date(2026, 1, 15)
        assert albums[0]["cover_xl"] == "https://img.com/1.jpg"

    @patch("ingesta.clients.deezer._get")
    def test_no_min_date_returns_all(self, mock_get):
        mock_get.return_value = {
            "data": [
                {
                    "id": 1,
                    "title": "A",
                    "release_date": "2020-01-01",
                    "cover_xl": "",
                    "record_type": "single",
                },
                {
                    "id": 2,
                    "title": "B",
                    "release_date": "2026-01-01",
                    "cover_xl": "",
                    "record_type": "album",
                },
            ],
            "next": None,
        }
        albums = get_artist_albums(1)
        assert len(albums) == 2

    @patch("ingesta.clients.deezer._get")
    def test_pagination(self, mock_get):
        mock_get.side_effect = [
            {
                "data": [
                    {
                        "id": 1,
                        "title": "A",
                        "release_date": "2026-01-01",
                        "cover_xl": "",
                        "record_type": "album",
                    }
                ],
                "next": "https://api.deezer.com/artist/1/albums?index=25",
            },
            {
                "data": [
                    {
                        "id": 2,
                        "title": "B",
                        "release_date": "2026-02-01",
                        "cover_xl": "",
                        "record_type": "single",
                    }
                ],
                "next": None,
            },
        ]
        albums = get_artist_albums(1)
        assert len(albums) == 2

    @patch("ingesta.clients.deezer._get")
    def test_api_error_returns_empty(self, mock_get):
        mock_get.return_value = None
        assert get_artist_albums(1) == []


class TestGetAlbumTracks:
    @patch("ingesta.clients.deezer._get")
    def test_returns_tracks_with_isrc(self, mock_get):
        # First call: album tracks listing
        # Second call: full track details
        mock_get.side_effect = [
            {
                "data": [
                    {
                        "id": 500,
                        "title": "La Cançó",
                        "duration": 210,
                        "artist": {"id": 98469, "name": "ZOO"},
                    },
                ]
            },
            {
                "id": 500,
                "title": "La Cançó",
                "isrc": "ES80D2511602",
            },
        ]

        tracks = get_album_tracks(100)

        assert len(tracks) == 1
        assert tracks[0]["title"] == "La Cançó"
        assert tracks[0]["isrc"] == "ES80D2511602"
        assert tracks[0]["duration"] == 210
        assert tracks[0]["artist_id"] == 98469

    @patch("ingesta.clients.deezer._get")
    def test_missing_isrc_returns_empty_string(self, mock_get):
        mock_get.side_effect = [
            {
                "data": [
                    {
                        "id": 500,
                        "title": "Track",
                        "duration": 180,
                        "artist": {"id": 1, "name": "A"},
                    },
                ]
            },
            {"id": 500, "title": "Track"},  # no isrc field
        ]

        tracks = get_album_tracks(100)
        assert tracks[0]["isrc"] == ""

    @patch("ingesta.clients.deezer._get")
    def test_api_error_returns_empty(self, mock_get):
        mock_get.return_value = None
        assert get_album_tracks(1) == []
