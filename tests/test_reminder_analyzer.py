import pytest
from app.services.reminder_analyzer import ReminderAnalyzer, ReminderAnalysis


class TestReminderAnalyzer:
    """Test cases for reminder analyzer."""
    
    def setup_method(self):
        self.analyzer = ReminderAnalyzer()
    
    def test_за_час_о_сходить_в_магазин(self):
        """Test: 'Уведоми за час о том что нужно сходить в магазин'"""
        result = self.analyzer.analyze("Уведоми за час о том что нужно сходить в магазин")
        
        assert result.reminder_text == "сходить в магазин"
        assert result.reminder_type == "relative"
        assert result.notification_time is None
        assert result.offset_minutes == 60
        assert result.confidence == 0.95
    
    def test_через_2_часа_позвонить_маме(self):
        """Test: 'Напомни через 2 часа позвонить маме'"""
        result = self.analyzer.analyze("Напомни через 2 часа позвонить маме")
        
        assert result.reminder_text == "позвонить маме"
        assert result.reminder_type == "relative"
        assert result.notification_time == "2h"
        assert result.offset_minutes == 0
        assert result.confidence == 0.99
    
    def test_завтра_в_18_00_сходить_в_спортзал(self):
        """Test: 'Напомни завтра в 18:00 сходить в спортзал'"""
        result = self.analyzer.analyze("Напомни завтра в 18:00 сходить в спортзал")
        
        assert result.reminder_text == "сходить в спортзал"
        assert result.reminder_type == "absolute"
        assert result.notification_time is not None
        # 18:00 Almaty = 13:00 UTC (UTC+5)
        assert "T13:00:00" in result.notification_time
        assert result.offset_minutes == 0
        assert result.confidence == 0.97
    
    def test_за_30_минут_до_встречи(self):
        """Test: 'Напомни за 30 минут до встречи'"""
        result = self.analyzer.analyze("Напомни за 30 минут до встречи")
        
        # The text "встречи" is extracted as-is (genitive case)
        assert result.reminder_text == "встречи"
        assert result.reminder_type == "relative"
        assert result.notification_time is None
        assert result.offset_minutes == 30
        assert result.confidence == 0.95
    
    def test_через_5_минут(self):
        """Test: 'через 5 минут'"""
        result = self.analyzer.analyze("Напомни через 5 минут")
        
        assert result.reminder_type == "relative"
        assert result.notification_time == "5m"
    
    def test_за_10_минут(self):
        """Test: 'за 10 минут'"""
        result = self.analyzer.analyze("Уведоми за 10 минут")
        
        assert result.reminder_type == "relative"
        assert result.offset_minutes == 10
    
    def test_спустя_полчаса(self):
        """Test: 'спустя полчаса'"""
        result = self.analyzer.analyze("Напомни спустя полчаса")
        
        assert result.reminder_type == "relative"
        assert result.notification_time == "30m"
    
    def test_через_час(self):
        """Test: 'через час'"""
        result = self.analyzer.analyze("Напомни через час")
        
        assert result.reminder_type == "relative"
        assert result.notification_time == "1h"
    
    def test_через_полтора_часа(self):
        """Test: 'через полтора часа'"""
        result = self.analyzer.analyze("Напомни через полтора часа")
        
        assert result.reminder_type == "relative"
        assert result.notification_time == "1.5h"
    
    def test_через_3_дня(self):
        """Test: 'через 3 дня'"""
        result = self.analyzer.analyze("Напомни через 3 дня")
        
        assert result.reminder_type == "relative"
        assert result.notification_time == "72h"  # 3 days = 72 hours
    
    def test_через_неделю(self):
        """Test: 'через неделю' - should be relative, not absolute"""
        result = self.analyzer.analyze("Напомни через неделю")
        
        assert result.reminder_type == "relative"
        assert result.notification_time == "168h"  # 1 week = 168 hours
    
    def test_25_мая_в_15_30(self):
        """Test: '25 мая в 15:30'"""
        result = self.analyzer.analyze("Напомни 25 мая в 15:30")
        
        assert result.reminder_type == "absolute"
        assert result.notification_time is not None
        assert "05-25" in result.notification_time
        # 15:30 Almaty = 10:30 UTC (UTC+5)
        assert "T10:30" in result.notification_time
    
    def test_25_05_2026(self):
        """Test: '25.05.2026'"""
        result = self.analyzer.analyze("Напомни 25.05.2026")
        
        assert result.reminder_type == "absolute"
        assert result.notification_time is not None
    
    def test_no_time_found(self):
        """Test: no time found - should default to 30 minutes"""
        result = self.analyzer.analyze("Напомни сделать задачу")
        
        assert result.reminder_type == "relative"
        assert result.notification_time == "30m"
    
    def test_через_две_недели(self):
        """Test: 'через две недели' - should be relative, not absolute"""
        result = self.analyzer.analyze("Напомни через две недели")
        
        assert result.reminder_type == "relative"
        assert result.notification_time == "336h"  # 2 weeks = 336 hours
    
    def test_в_8_30_сходить_в_магазин_за_15_минут(self):
        """Test: 'в 8:30 сходить в магазин напомни за 15 минут' - combined time+offset"""
        result = self.analyzer.analyze("в 8:30 сходить в магазин напомни за 15 минут")
        
        assert result.reminder_text == "сходить в магазин"
        assert result.reminder_type == "absolute"
        assert result.offset_minutes == 15
        assert result.event_time is not None
        # 8:30 Almaty = 3:30 UTC (UTC+5), but since it's in the past, it's tomorrow
        # So 8:30 tomorrow Almaty = 3:30 UTC next day
        assert "T03:30:00" in result.event_time
        # Notification time should be 15 minutes before 8:30, i.e., 8:15
        # 8:15 Almaty = 3:15 UTC
        assert "T03:15:00" in result.notification_time
        assert result.confidence == 0.98
    
    def test_завтра_в_8_30_сходить_в_магазин_за_15_минут(self):
        """Test: 'завтра в 8:30 сходить в магазин напомни за 15 минут' - tomorrow with offset"""
        result = self.analyzer.analyze("завтра в 8:30 сходить в магазин напомни за 15 минут")
        
        assert result.reminder_text == "сходить в магазин"
        assert result.reminder_type == "absolute"
        assert result.offset_minutes == 15
        assert result.event_time is not None
        # 8:30 Almaty = 3:30 UTC (UTC+5)
        assert "T03:30:00" in result.event_time
        # Notification time should be 15 minutes before 8:30, i.e., 8:15
        # 8:15 Almaty = 3:15 UTC
        assert "T03:15:00" in result.notification_time
        assert result.confidence == 0.98
    
    def test_25_мая_в_15_30_встреча_за_30_минут(self):
        """Test: '25 мая в 15:30 встреча напомни за 30 минут' - date with time and offset"""
        result = self.analyzer.analyze("25 мая в 15:30 встреча напомни за 30 минут")
        
        assert result.reminder_text == "встреча"
        assert result.reminder_type == "absolute"
        assert result.offset_minutes == 30
        assert result.event_time is not None
        assert "05-25" in result.event_time
        # 15:30 Almaty = 10:30 UTC (UTC+5)
        assert "T10:30:00" in result.event_time
        # Notification time should be 30 minutes before 15:30, i.e., 15:00
        # 15:00 Almaty = 10:00 UTC
        assert "T10:00:00" in result.notification_time
        assert result.confidence == 0.98
    
    def test_25_05_2026_в_10_00_за_1_час(self):
        """Test: '25.05.2026 в 10:00 встреча напомни за 1 час' - full date with time and offset"""
        result = self.analyzer.analyze("25.05.2026 в 10:00 встреча напомни за 1 час")
        
        assert result.reminder_text == "встреча"
        assert result.reminder_type == "absolute"
        assert result.offset_minutes == 60
        assert result.event_time is not None
        assert "2026-05-25" in result.event_time
        # 10:00 Almaty = 5:00 UTC (UTC+5)
        assert "T05:00:00" in result.event_time
        # Notification time should be 1 hour before 10:00, i.e., 9:00
        # 9:00 Almaty = 4:00 UTC
        assert "T04:00:00" in result.notification_time
        assert result.confidence == 0.98
    
    def test_в_11_00_сходить_в_магазин_уведоми_в_9_30(self):
        """Test: 'в 11 00 сходить в магазин, уведоми в 9 30' - two explicit times pattern"""
        result = self.analyzer.analyze("в 11 00 сходить в магазин, уведоми в 9 30")
        
        assert result.reminder_text == "сходить в магазин,"
        assert result.reminder_type == "absolute"
        assert result.event_time is not None
        # 11:00 Almaty = 6:00 UTC (UTC+5)
        assert "T06:00:00" in result.event_time
        # Notification time should be 9:30
        # 9:30 Almaty = 4:30 UTC
        assert "T04:30:00" in result.notification_time
        # Offset should be 1.5 hours (90 minutes)
        assert result.offset_minutes == 90
        assert result.confidence == 0.98