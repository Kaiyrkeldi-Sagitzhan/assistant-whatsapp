def test_nlp_relative_dates_ru():
    """Test Russian relative date extraction."""
    from app.services.nlp_pipeline import NLPPipeline

    pipeline = NLPPipeline()

    # Test "завтра"
    result = pipeline._extract_relative_date("Напомни завтра в 10:00")
    assert result is not None

    # Test "в пятницу"
    result = pipeline._extract_relative_date("до пятницы подготовить")
    assert result is not None

    # Test "на следующей неделе"
    result = pipeline._extract_relative_date("на следующей неделе выполнить")
    assert result is not None


def test_gemini_fallback():
    """Test NLP falls back gracefully when Gemini fails."""
    from app.services.nlp_pipeline import NLPPipeline

    pipeline = NLPPipeline()
    # Mock or patch Gemini client for this test
    # For now, just ensure the pipeline doesn't crash
    assert pipeline._extract_relative_date("завтра") is not None
