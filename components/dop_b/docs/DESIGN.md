# Tasarım ve operatör sözleşmesi

Hedef az kelimeyle açık işlevdir. Metni azaltmak bütün ekranları tek tipe ezmek anlamına gelmez. Makine durumları, eylemler, alarm, feedback ve navigasyon operatör tarafından ayırt edilebilir olmalıdır.

DESIGN_BRIEF target profile, operatör görevi, ekran hiyerarşisi, nesne geometry/style, language/font, tag bindings ve behavior sözleşmesini taşır. Her yazı/nesne/dosyanın bir owner'ı vardır; ortak tag kataloğu paralel değiştirilmez.

Shared IR kökü `schema_version: 1`, `project_id`, `profile_id`, `screens`, `tags`, `macros`, `alarms` alanlarıdır. Screen `id/name/width/height/elements` taşır. Element türleri `text/button/numeric_input/numeric_display/indicator/goto/alarm_strip/alarm_table/alarm_history`; bindings exact `read/write` tag ID'leridir. Numeric contract `minimum/maximum/fractional/format: decimal/unit/unit_label` alanlarını ayrı tutar. Tag `id/address/data_type/access/unit` ile tanımlanır; neutral demo adresi gerçek vendor adresi sayılmaz. IR destekli element native patcher'da otomatik supported olmaz.

`render_preview` sample `values` (tag ID→numeric) ve `states` (tag ID→valid/invalid/stale) alabilir. Eksik, invalid, stale veya type/range dışı veri gri **UNKNOWN** gösterir. Sample control'ler görselin dışındadır; çizilen button/goto/macro tıklaması gerçek komut veya native davranış yürütmez. Preview validation issues içerir; issues görünmesi veya render oluşması kabul değildir.

## Sayısal birimin tek yazı sahibi

Numeric input/display `unit_label` ile aynı sayfadaki exact, tekil bir `text` element ID'sine bağlanabilir. Bir text element yalnız bir numeric owner'a aittir; relation sıra bağımsızdır ve tam design hash'ine dahildir. Numeric `unit` açık, boş olmayan literal olmalı; bound tag'in `unit` değeri ve text owner's `text` değeriyle karakter karakter eşleşmelidir. Numeric input'ın read/write binding'i aynı process tag'ini, type ve unit'i temsil eder; birim dönüşümü yapılmaz.

Text owner kendi `x/y/width/height/font_size/color/fill` alanlarını açıkça taşır. Binding, state veya başka `unit_label` taşımaz; self-reference, cross-page, duplicate/shared owner ve reference chain kabul edilmez. Mevcut bounds/overlap/font/color validation kapıları bu nesneye de uygulanır. Relation eksik/yanlışsa preview numeric değerini `UNKNOWN / UNIT LABEL INVALID` tutar; sample controls bunu geçerli duruma çeviremez.

Kavramsal preview yalnız `unit_label` relation'ı bildirilen numeric elementin inline unit'ini bastırır; relation olmayan mevcut tasarımlar eski inline görünümü korur. Ayrı text owner kendi geometry/style'ında tek kez çizilir. Browser DOM, linked text'in gerçek glyph bounds'ını declared font size ile ölçer; sığmıyorsa `INSUFFICIENT SPACE` ve layout issue üretir, fontu küçültmez. Tam literal design'da ve overflow title'ında tutulur. CRLF/NUL içeren ID'lerin HTML tarafından normalize edilmesi fit veya invalid-owner kontrolünü atlatamaz: bu kontroller DOM ID karşılaştırması yerine stable numeric element index kullanır.

Bu relation bir **unit compiler subset**'idir. Public synthetic native transaction ayrıca exact source-local numeric/text donor, ordinary text font/color contract ve inactive embedded-unit identity baseline ister; [mimari](ARCHITECTURE.md#numeric-unit-compiler-subset) bu ayrı gate'i tanımlar. Conceptual browser font/overflow sonucu native `UnitDirection`, font units, enum, glyph veya pixel qualification değildir. Gerçek selected-model unit compiler ile public Alarm IR/view/history geliştirmesi ve tam V1 kabulü açıktır. Mevcut examples değiştirilmemiştir; relation olmayan examples yeni unit subset'inin kanıtı sayılmaz.

## İşlev ve durum

- Komut kontrolü ve feedback indicator ayrı semantics'tir. Komut biti fiziksel durum kanıtı olmaz.
- Momentary, maintained ve toggle açık contract'tir; sessizce birbirine çevrilmez.
- Disconnected, stale, unknown ve normal/off ayrı gösterilir. Haberleşme kaybı "kapalı/sağlıklı" değildir.
- Tip/adres/driver/width/scale/unit kaynak kanıtına bağlıdır. Üst sınır veya byte offset adres yerine alınmaz; tam adres kimliği eşleşir.
- TIME yeniden adlandırılarak veya 64-bit daraltılarak destek üretilmez. Kanıtsız mapping açık validation hatasıdır.
- Nesne sınırları, çakışma, metin sığması, contrast ve operator viewing distance değerlendirilir. Default font veya renkten vendor garanti çıkarılmaz.

## Görsel ve inceleme sırası

1. Uygulayıcı sürümlü preview üretir; **CONCEPTUAL_SYNTHETIC** veya **NATIVE_PROFILE** render türünü görünür yazar. Native desteği olmayan layer gizlenerek PASS alınmaz.
2. Teknik reviewer read-only kaynak/type/address/behavior ve güvenlik kabulünü inceler.
3. AESTHETIC_FIRST operatör görevleri, hiyerarşi, readability, state ayrımı ve gereksiz metni değerlendirir.
4. AESTHETIC_SECOND ilk raporu okuduktan sonra tasarımı, uygulayıcı kararlarını ve ilk reviewer'ın kör noktalarını eleştirir.
5. En çok bir odaklı estetik repair ve tekrar review. Önemli estetik açık kalırsa STOP; fonksiyonel hatayı bu sayıya dayanarak kabul etme.
6. İnsan sürümlü preview ve target/design/binding/behavior/source hash'lerine onay verir. Bu contract değişirse onay yenilenir.

İncelemeler bulgu zincirini [REVIEW_CHAIN](../templates/REVIEW_CHAIN.json) biçiminde taşır. Kanıtsız reviewer uzlaşması kabul değildir. Synthetic ortak pilot iki profile için paylaşılabilir; kavramsal taslak native üretim dosyası olarak sunulmaz. Qualified schema/vendor fixture yokken generic native mutation kapısı açılmaz.
