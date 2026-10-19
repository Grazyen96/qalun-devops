import pytest

from qalun_web.pipeline import surah_name, surahs


def test_all_114_surahs_are_listed_in_order():
    numbers = [surah["surah_num"] for surah in surahs()]

    assert numbers == list(range(1, 115))


def test_a_surah_number_becomes_the_name_the_range_search_filters_by():
    # Al-Furqan, as the text that ships with QuranText spells it.
    assert "الفُرقَانِ" in surah_name(25)


def test_a_number_outside_the_quran_is_refused():
    with pytest.raises(ValueError, match="115"):
        surah_name(115)
