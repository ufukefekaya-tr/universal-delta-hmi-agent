# Alarm ve görünüm — kaynak gözlemi sınırı

Uygulama özgün `SYNTHETIC/0.0` fixture'larla geliştirilmiştir. Kurulu vendor örnekleri salt okunur bellekte incelenmiş; dosyalar, varlıklar, özel yollar veya müşteri bilgileri repoya alınmamıştır. Native aday ve vendor IDE işlemi yapılmamıştır.

Type11/SubType1 geçmiş, 2 current ve 4 strip bölüm biçimleri gözlenmiştir. Global `[Alarm]` tablosu görünümden ayrı kaynaktır; `[History]` ayrıca process sampling verisi taşıyabilir. İkisini bir alarm geçmişi deposu gibi birleştiren dönüşüm üretilmez.

Global `Hold` / `AlmHoldPlace`, tarih/saat, sütun, font, grup ve hareket enumları için differential vendor kalibrasyonu yoktur. Kaynak raw byte'larının korunması bu alanların çalışma anlamını kanıtlamaz. `preserve_source` politikasının nedeni budur: native sahibin geometri dışındaki bütün kayıtları korunur ve kavramsal önizleme gerçek vendor görünümünü çizdiğini söylemez.

Bağımsız inceleme, üç gerçek dosyada no-op byte eşitliğini ve kaynakların değişmediğini doğruladı. AlarmEN'deki current/history sahipleri `GroupIDVariation`, FullDemo'daki current/history/strip sahipleri `GroupID` nedeniyle dar referans sözleşmesinde kapalı kaldı. Frequency subtype3 desteklenmez. History örneğinde Type11 görünüm ve etkin alarm bulunmadı. **Bu holdout'lar genuine alarm-view context PASS değildir.** Yeni helper'ı corpus'a uydurmak için belirsiz referans kontrolü gevşetilmedi.

Application'da gözlenen `AlarmMsgWarpText`, `FDA_AlarmEnable`, `DiskSpaceAlarmEnable`, `ShowUsbMsgInAlarm` ve `AlarmExportCSV` global alanları korunur; Type11'e ait foreign owner alanlarıyla aynı sayılmaz. SC Alarm örneğinde bazı BOOL kayıtlar explicit `AlarmOn` / `AlarmMemLen` companion alanlarından yoksundur; public semantic mapping bu boşlukları default ile doldurmaz.

Kaynak fingerprint ve bağımsız sonuç ayrıntıları [milestone](NATIVE_ALARM_VIEW_MILESTONE.json) ve [son denetimde](NATIVE_ALARM_VIEW_REVIEW.md) tutulur. Seçilmiş DOP-B07S411 / DOP-110IS model kalibrasyonu, haricî sürücü, native piksel, vendor derleme ve panel kabulü açık kalır.
