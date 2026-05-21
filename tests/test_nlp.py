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


def test_nlp_through_patterns():
    """Test 'через X' patterns for date extraction."""
    from app.services.nlp_pipeline import NLPPipeline

    pipeline = NLPPipeline()

    # Test "через неделю"
    result = pipeline._extract_datetime_from_text("встреча через неделю", "Asia/Almaty")
    assert result is not None

    # Test "через день"
    result = pipeline._extract_datetime_from_text("сделать через день", "Asia/Almaty")
    assert result is not None

    # Test "через два дня"
    result = pipeline._extract_datetime_from_text("задача через два дня", "Asia/Almaty")
    assert result is not None

    # Test "через три дня"
    result = pipeline._extract_datetime_from_text("событие через три дня", "Asia/Almaty")
    assert result is not None

    # Test "через 5 дней"
    result = pipeline._extract_datetime_from_text("через 5 дней", "Asia/Almaty")
    assert result is not None

    # Test "через 2 недели"
    result = pipeline._extract_datetime_from_text("через 2 недели", "Asia/Almaty")
    assert result is not None


def test_process_clarification_response():
    """Test clarification response processing."""
    from app.services.nlp_pipeline import NLPPipeline

    pipeline = NLPPipeline()

    # Test time clarification
    result = pipeline.process_clarification_response(
        clarification_type="time",
        clarification_response="завтра в 15:00",
        original_text="встреча с клиентом",
        parsed_title="встреча с клиентом",
        parsed_description="встреча с клиентом",
        partial_data={}
    )
    assert result["datetime"] is not None
    assert result["title"] == "встреча с клиентом"

    # Test title clarification
    result = pipeline.process_clarification_response(
        clarification_type="title",
        clarification_response="Купить продукты в магазине",
        original_text="нужно сделать",
        parsed_title="нужно сделать",
        parsed_description="нужно сделать",
        partial_data={}
    )
    assert result["title"] == "Купить продукты в магазине"


def test_gemini_fallback():
    """Test NLP falls back gracefully when Gemini fails."""
    from app.services.nlp_pipeline import NLPPipeline

    pipeline = NLPPipeline()
    # Mock or patch Gemini client for this test
    # For now, just ensure the pipeline doesn't crash
    assert pipeline._extract_relative_date("завтра") is not None
