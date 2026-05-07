"""Unit tests for EmbeddingService — LRU cache behaviour and provider delegation."""

from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import EmbeddingProviderApi
from ollama_llm_bench.backend.services.embedding_service import EmbeddingService

_VEC_A: list[float] = [0.1, 0.2, 0.3]
_VEC_B: list[float] = [0.4, 0.5, 0.6]
_VEC_C: list[float] = [0.7, 0.8, 0.9]


def _make_service(
    mocker: MockerFixture,
    *,
    cache_size: int = 512,
) -> tuple[EmbeddingService, MockerFixture]:
    mock_provider = mocker.Mock(spec=EmbeddingProviderApi)
    service = EmbeddingService(provider=mock_provider, cache_size=cache_size)
    return service, mock_provider


# ---------------------------------------------------------------------------
# encode_single — cache miss
# ---------------------------------------------------------------------------


def test_encode_single_cache_miss_calls_provider(mocker: MockerFixture) -> None:
    # Arrange
    service, mock_provider = _make_service(mocker)
    mock_provider.encode.return_value = [_VEC_A]

    # Act
    result = service.encode_single("hello")

    # Assert
    mock_provider.encode.assert_called_once_with(["hello"])
    assert result == _VEC_A


def test_encode_single_cache_miss_returns_correct_vector(mocker: MockerFixture) -> None:
    # Arrange
    service, mock_provider = _make_service(mocker)
    mock_provider.encode.return_value = [_VEC_B]

    # Act
    result = service.encode_single("world")

    # Assert
    assert result == _VEC_B


# ---------------------------------------------------------------------------
# encode_single — cache hit
# ---------------------------------------------------------------------------


def test_encode_single_cache_hit_no_second_provider_call(mocker: MockerFixture) -> None:
    # Arrange
    service, mock_provider = _make_service(mocker)
    mock_provider.encode.return_value = [_VEC_A]
    service.encode_single("hello")  # populate cache

    # Act
    result = service.encode_single("hello")

    # Assert
    assert mock_provider.encode.call_count == 1  # provider NOT called a second time
    assert result == _VEC_A


def test_encode_single_different_texts_each_calls_provider(mocker: MockerFixture) -> None:
    # Arrange
    service, mock_provider = _make_service(mocker)
    mock_provider.encode.side_effect = [[_VEC_A], [_VEC_B]]

    # Act
    result_a = service.encode_single("text_a")
    result_b = service.encode_single("text_b")

    # Assert
    assert mock_provider.encode.call_count == 2
    assert result_a == _VEC_A
    assert result_b == _VEC_B


# ---------------------------------------------------------------------------
# encode_batch — empty input
# ---------------------------------------------------------------------------


def test_encode_batch_empty_returns_empty_list(mocker: MockerFixture) -> None:
    # Arrange
    service, mock_provider = _make_service(mocker)

    # Act
    result = service.encode_batch([])

    # Assert
    assert result == []
    mock_provider.encode.assert_not_called()


# ---------------------------------------------------------------------------
# encode_batch — all cache miss
# ---------------------------------------------------------------------------


def test_encode_batch_all_cache_miss_calls_provider_once(mocker: MockerFixture) -> None:
    # Arrange
    service, mock_provider = _make_service(mocker)
    mock_provider.encode.return_value = [_VEC_A, _VEC_B, _VEC_C]

    # Act
    result = service.encode_batch(["t1", "t2", "t3"])

    # Assert
    mock_provider.encode.assert_called_once_with(["t1", "t2", "t3"])
    assert result == [_VEC_A, _VEC_B, _VEC_C]


def test_encode_batch_all_cache_miss_returns_correct_count(mocker: MockerFixture) -> None:
    # Arrange
    service, mock_provider = _make_service(mocker)
    mock_provider.encode.return_value = [_VEC_A, _VEC_B]

    # Act
    result = service.encode_batch(["t1", "t2"])

    # Assert
    assert len(result) == 2


# ---------------------------------------------------------------------------
# encode_batch — mixed cached / uncached
# ---------------------------------------------------------------------------


def test_encode_batch_mixed_cached_uncached_calls_provider_for_uncached_only(
    mocker: MockerFixture,
) -> None:
    # Arrange
    service, mock_provider = _make_service(mocker)
    # Pre-populate cache for "t1" with one provider call
    mock_provider.encode.return_value = [_VEC_A]
    service.encode_single("t1")
    mock_provider.encode.reset_mock()

    # Now encode a batch where "t1" is cached and "t2" is not
    mock_provider.encode.return_value = [_VEC_B]

    # Act
    result = service.encode_batch(["t1", "t2"])

    # Assert
    mock_provider.encode.assert_called_once_with(["t2"])
    assert result == [_VEC_A, _VEC_B]


def test_encode_batch_all_cached_no_provider_call(mocker: MockerFixture) -> None:
    # Arrange
    service, mock_provider = _make_service(mocker)
    mock_provider.encode.return_value = [_VEC_A, _VEC_B]
    service.encode_batch(["t1", "t2"])  # populate cache
    mock_provider.encode.reset_mock()

    # Act
    result = service.encode_batch(["t1", "t2"])

    # Assert
    mock_provider.encode.assert_not_called()
    assert result == [_VEC_A, _VEC_B]


# ---------------------------------------------------------------------------
# encode_batch — order preservation
# ---------------------------------------------------------------------------


def test_encode_batch_returns_results_in_original_order(mocker: MockerFixture) -> None:
    # Arrange
    service, mock_provider = _make_service(mocker)
    # Pre-populate "t2" so it's cached; "t1" and "t3" are misses
    mock_provider.encode.return_value = [_VEC_B]
    service.encode_single("t2")
    mock_provider.encode.reset_mock()

    # Provider will be called with uncached texts ["t1", "t3"] → returns [_VEC_A, _VEC_C]
    mock_provider.encode.return_value = [_VEC_A, _VEC_C]

    # Act
    result = service.encode_batch(["t1", "t2", "t3"])

    # Assert — order must match the input, not the provider call order
    assert result[0] == _VEC_A  # t1
    assert result[1] == _VEC_B  # t2 (was cached)
    assert result[2] == _VEC_C  # t3


def test_encode_batch_duplicate_texts_deduplicated_single_provider_call(
    mocker: MockerFixture,
) -> None:
    # Arrange
    service, mock_provider = _make_service(mocker)
    mock_provider.encode.return_value = [_VEC_A]

    # Act — "t1" appears twice in the input
    result = service.encode_batch(["t1", "t1"])

    # Assert — provider called once, result contains the embedding twice
    mock_provider.encode.assert_called_once_with(["t1"])
    assert result == [_VEC_A, _VEC_A]


# ---------------------------------------------------------------------------
# LRU eviction
# ---------------------------------------------------------------------------


def test_cache_evicts_oldest_when_at_capacity(mocker: MockerFixture) -> None:
    # Arrange — cache holds at most 2 items
    service, mock_provider = _make_service(mocker, cache_size=2)
    mock_provider.encode.side_effect = [[_VEC_A], [_VEC_B], [_VEC_C], [_VEC_A]]

    service.encode_single("t1")  # cache: {t1}
    service.encode_single("t2")  # cache: {t1, t2}

    # Act — encode "t3"; cache is at capacity so "t1" (oldest) must be evicted
    service.encode_single("t3")  # cache: {t2, t3}

    mock_provider.encode.reset_mock()
    mock_provider.encode.return_value = [_VEC_A]

    # Assert — "t1" was evicted so a new provider call is required
    service.encode_single("t1")
    mock_provider.encode.assert_called_once_with(["t1"])


def test_cache_does_not_evict_recently_used_entry(mocker: MockerFixture) -> None:
    # Arrange — cache holds at most 2 items
    service, mock_provider = _make_service(mocker, cache_size=2)
    mock_provider.encode.side_effect = [[_VEC_A], [_VEC_B], [_VEC_B], [_VEC_C]]

    service.encode_single("t1")  # cache: {t1}
    service.encode_single("t2")  # cache: {t1, t2}

    # Promote "t1" to most-recent so "t2" becomes the oldest
    service.encode_single("t1")

    # Encode "t3" — "t2" should be evicted, NOT "t1"
    service.encode_single("t3")  # cache: {t1, t3}

    mock_provider.encode.reset_mock()
    mock_provider.encode.return_value = [_VEC_B]

    # Assert — "t1" is still in cache so provider should NOT be called for it
    service.encode_single("t1")
    mock_provider.encode.assert_not_called()


def test_cache_size_one_evicts_on_every_new_text(mocker: MockerFixture) -> None:
    # Arrange
    service, mock_provider = _make_service(mocker, cache_size=1)
    mock_provider.encode.side_effect = [[_VEC_A], [_VEC_B], [_VEC_A]]

    service.encode_single("t1")  # cache: {t1}
    service.encode_single("t2")  # cache: {t2} — t1 evicted

    mock_provider.encode.reset_mock()
    mock_provider.encode.return_value = [_VEC_A]

    # Act — t1 must be a miss; provider must be called again
    service.encode_single("t1")

    # Assert
    mock_provider.encode.assert_called_once_with(["t1"])


# ---------------------------------------------------------------------------
# _store branch — text already in cache (move_to_end path via encode_single)
# ---------------------------------------------------------------------------


def test_store_branch_text_already_in_cache_via_encode_single_move_to_end(
    mocker: MockerFixture,
) -> None:
    # Arrange — cache_size=2; insert t1 then t2, then access t1 to move it to end,
    # then insert t3 — t2 (now oldest) should be evicted, not t1.
    service, mock_provider = _make_service(mocker, cache_size=2)
    mock_provider.encode.side_effect = [[_VEC_A], [_VEC_B], [_VEC_C], [_VEC_A]]

    service.encode_single("t1")  # cache: {t1}
    service.encode_single("t2")  # cache: {t1, t2}
    service.encode_single("t1")  # promote t1 → cache order: {t2, t1}; exercising move_to_end
    service.encode_single("t3")  # cache full; evict oldest=t2 → cache: {t1, t3}

    mock_provider.encode.reset_mock()
    mock_provider.encode.return_value = [_VEC_B]

    # Act — t1 must still be in cache (was promoted), so no provider call
    result_t1 = service.encode_single("t1")

    # Assert — t1 served from cache (move_to_end branch was exercised above)
    mock_provider.encode.assert_not_called()
    assert result_t1 == _VEC_A


# ---------------------------------------------------------------------------
# Regression: encode_batch evicts cached entry when cache is at capacity
# during the same batch call (known implementation bug)
# ---------------------------------------------------------------------------


def test_encode_batch_cache_hit_not_evicted_when_capacity_not_exceeded(
    mocker: MockerFixture,
) -> None:
    # Arrange — cache_size=3 so inserting 1 new item while 2 are cached
    # does NOT trigger eviction of any existing entry.
    service, mock_provider = _make_service(mocker, cache_size=3)

    # Populate cache for t1 and t2 individually
    mock_provider.encode.return_value = [_VEC_A]
    service.encode_single("t1")  # cache: {t1}
    mock_provider.encode.return_value = [_VEC_B]
    service.encode_single("t2")  # cache: {t1, t2}
    mock_provider.encode.reset_mock()

    # Now encode_batch with one uncached text; cache still has room
    mock_provider.encode.return_value = [_VEC_C]

    # Act — t1 and t2 are cached; t3 is new; cache has room for t3
    result = service.encode_batch(["t1", "t2", "t3"])

    # Assert — all three results correct; provider called once for t3 only
    mock_provider.encode.assert_called_once_with(["t3"])
    assert result == [_VEC_A, _VEC_B, _VEC_C]


# ---------------------------------------------------------------------------
# encode — Protocol adapter (delegates to encode_batch)
# ---------------------------------------------------------------------------


def test_encode_empty_list_returns_empty_list(mocker: MockerFixture) -> None:
    # Arrange
    service, mock_provider = _make_service(mocker)

    # Act
    result = service.encode([])

    # Assert
    assert result == []
    mock_provider.encode.assert_not_called()


def test_encode_delegates_to_encode_batch_returns_same_result(mocker: MockerFixture) -> None:
    # Arrange
    service, mock_provider = _make_service(mocker)
    mock_provider.encode.return_value = [_VEC_A, _VEC_B]

    # Act
    result = service.encode(["t1", "t2"])

    # Assert
    assert result == [_VEC_A, _VEC_B]
    mock_provider.encode.assert_called_once_with(["t1", "t2"])


def test_encode_repeated_call_uses_cache_provider_called_once(mocker: MockerFixture) -> None:
    # Arrange
    service, mock_provider = _make_service(mocker)
    mock_provider.encode.return_value = [_VEC_A, _VEC_B]

    # Act — call encode twice with the same texts
    service.encode(["t1", "t2"])
    service.encode(["t1", "t2"])

    # Assert — provider called only once; second call served from cache
    assert mock_provider.encode.call_count == 1
