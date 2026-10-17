# Üç kaynakla çok sayfalı program adayı

`multipage_program_v1`, boş bir hedefe aynı modelden kaynakla doğrulanmış kontroller, metinler, BOOL göstergeler ve sayfa geçişleri yerleştirir. İlk gerçek dosya deneyi DOP-B10S615 / serialized `4.00.07.04` /1024×600 içindir. Bu, bütün DOP-B ailesinin veya vendor çalışma davranışının kabulü değildir.

## Kaynakların ayrı sorumluluğu

1. Boş hedef: çıktı globals, haberleşme yapılandırması, thumbnail, kaynaklar ve mevcut ilk sayfa başlığı/Aux sahibi.
2. Orijinal altı kontrol kütüphanesi: set-on, set-off, momentary, maintained, UINT input ve UINT display donor sahibi. Her biri exact source/property SHA ile kalibre edilir.
3. Ayrı yardımcı kütüphane: ordinary page template ve yalnız ayrı pinlenmiş Type10/SubType6 literal, Type2/SubType1 bit indicator, Type1/SubType10 goto extent'leri.

Yardımcı dosyanın globals veya eski kontrol owner'ları hedefe aktarılmaz. Gerçek vendor referansının ilk yeniden kaydı HMIPortNr0 alanını2'den1660265583'e ve eski numeric font oranlarını değiştirdi. Bu kaydın bütünüyle güvenilir kütüphane kabul edilmesi driver/veri kaybı yaratırdı. Yeni nesneler kaynağın yalnız sahibi bilinen bölümlerinden alınır; hedefin ayarları exact kalır.

Paylaşılan `profiles/layout_contracts` içindeki tarafsız kayıt model/sürüm, yardımcı kaynak SHA, page/header/Aux, üç owner ve property SHA'larını taşır. Vendor dosyaları, görüntüleri, erişilebilirlik dökümleri veya bilgisayar yolları genel repoya alınmaz. Bir profil içindeki `qualified:true`, kayıtlı kaynağın yerini alamaz. Sözleşme dosyaları başka host'a relative workspace yollarıyla taşınabilir; kurulu vendor programı MCP çalışması için çağrılmaz.

## Sınırlar ve gerçek native karşılıklar

| Niyet | Kaynakla doğrulanan karşılık | Açık kabul |
|---|---|---|
| Yeni normal sayfa | uint16 kimlik1–65535, boş Aux, inherited boyut, ScreenAction0; ilk sayfa exact korunur | Gerçek açma/derleme/gezinme |
| Literal | Türkçe primary UTF-16LE caption, bir State0; live operand yok | Native font/piksel |
| BOOL gösterge | Type2/Sub1, bit read, WriteVarNone, exact State.Value0/1; action callback yok | PLC/touch/communication-loss/runtime |
| Goto | Type1/Sub10, final uint16 destination ve doğru ASCII name companion; live/trigger/macro yok | Sayfa geçişinin panelde çalışması |
| Kontroller | Orijinal altı kontrol donor'u ve eski strict davranış/shape guard | Basma/bırakma, IDE/simülasyon/panel |
| Sayılar | UINT inputF0; ayrı sözleşmeyle UINT fixed-decimal displayF0–4/I+F≤5 | Signed/floating/TIME, fractional input/keypad |

Program en çok256 sayfa/4096 yeni owner taşır. Owner kimlikleri bütün çıktı genelinde benzersizdir; altı kontrol donor kimliği rezerv kalır. Page adları servis niyetinde en çok128 printable ASCII karakterdir. Native metin caption'ları Türkçe olabilir. Renkler yalnız R=B olan24-bit değerlerdir; tam RGB/COLORREF sırası bu milestone ile açılmaz. FontSize0 1–128 değişebilir; FontName/FontRatio/align/picture/animation/sound alanları donor byte'larıyla korunur. Tam stil tasarımı veya native render PASS değildir.

Gösterge IR'de `role:request` veya `role:feedback`, yalnız `binding.read` ve ordered `states:[{value:0,text,fill},{value:1,text,fill}]` ister. Komut isteği fiziksel çalışma bilgisine dönüştürülmez. Native haberleşme kaybını UNKNOWN gösterecek maskeleme bu üretim modunda henüz yoktur; dosya testi bu koşulu sağlıklı/kapalı diye kabul etmez. Kavramsal preview'daki kalite senaryosu native PLC davranışı değildir.

## Hazırlık ve dokuz MCP aracı

Önce [altı kontrol kalibrasyonu](CONTROL_GENERATION.md), gerekirse [driver adresleri](DRIVER_ADDRESSES.md) ve [ondalıklı display](FIXED_DECIMAL.md) hazırlanır. Üç kaynak aynı model/sürüm ve kabul edilen blank-control lineage içinde olmalıdır. Yardımcı kaynağın globals lineage'ı aktarım gerekçesi değildir; yalnız kayıtlı typed extent'ler kullanılır.

```text
python scripts/calibrate_multipage.py --workspace "projects/<project>" --target "inputs/blank.dps" --controls "library/controls.dps" --controls-profile "contracts/controls/profiles/source_controls_v1.json" --layout "library/layout.dps" --indicator-property "evidence/indicator.json" --text-property "evidence/text.json" --goto-property "evidence/goto.json" --output-dir "contracts/multipage-v001" --source-reference "inputs/PROVENANCE.md" --review-reference "reviews/layout.md"
python -m universal_hmi.cli --profiles "projects/<project>/contracts/multipage-v001/profiles" serve --workspace "projects/<project>"
```

İlk komut yalnız JSON witness/profile üretir; yeni native dosya veya insan tasarım onayı üretmez. Layout kaynağı ve property JSON'ları bir exact registered authority ile eşleşmezse dosya yazılmaz. Üç native kaynak, kontrol profili/calibration, bütün property witness'leri ve driver/numeric/layout registry dosyaları her plan/apply/save öncesi SHA/boyutla yeniden kontrol edilir. Girdi değişirse eski onay kullanılmaz; mevcut dosyanın üzerine yazılmaz.

`open_project` profile_id `multipage_program_v1` ve gerçek blank source_path alır. IR, ilk blank sayfayı aynı kimlik/isimle içerir; yeni ordinary sayfaları ve her sayfanın tam owner sırasını belirtir. Kaynak donor owner'ları IR'ye eklenmez. `plan_changes` operations omitted/null olduğunda tam graph deklarasyonu, orijinal kontrol klon/bind/settings ve auxiliary creation işlemlerini türetir. Goto `target_screen`, mantıksal IR page id'sidir; service onu native_id ve name'e birlikte çevirir.

İşlem protokolü `set_program_layout` ile tam sayfa/owner grafiğini bildirir; yalnız bu grafikteki nesneler oluşturulabilir. Tekrar çağrı duplicate oluşturmaz. `create_aux` metin/goto/indicator için exact alan kümesi kullanır. Açık operations aynı IR beklentisiyle karşılaştırılır; ek sahibi, değiştirilmiş durum, dangling hedef veya yanlış sıralama reddedilir. Malformed JSON discriminator'ları ham exception yerine typed HmiError üretir.

`preview` **CONCEPTUAL_IR**'dir. Makine projesinde teknik denetim, iki sıralı estetik uzman ve exact tasarım/hedef/adres/davranış hash'lerine bağlı insan onayı gerekir. Tarafsız adaptör örneği, makine onayı sayılmaz. `validate → apply_plan → save_as → diff` yalnız kabul edilen kapsamda offline native candidate üretir; yeni kaynak/profile ile çalışan sunucu süreci yeniden başlatılır.

## Kaydetme ve bağımsız karşılaştırma

Emitter, altı kontrolü geçici orijinal kaynak bağlamında strict doğrular ve yalnız yeni owner extent'lerini final sayfalara yerleştirir. Native verifier kaydedilmiş dosyanın bütün page/header/Aux/owner grafiğini, managed/unmanaged kayıtlarını, salt okunur göstergeyi ve final goto ilişkilerini kontrol eder. Service operasyon emitter'ını kullanmadan ayrı IR→raw expected body üretir; **bütün** saved body ile karşılaştırır. Native shape doğrulaması tek başına onaylı niyet kanıtı değildir.

Hedef prefix37/BMP/globals korunur; son length DWORD decoded body uzunluğuna göre güncellenir. Bound indicator veya altı kontrolden birinin bulunduğu çıktı, blank→controls kaydında gözlenen owned empty Tag initialization'ı kullanır. Sadece page/text/goto bulunan çıktı hedef tail'ini exact tutar. Boş tek orijinal sayfa ve sıfır owner bir dosya no-op'udur; bütün byte'lar korunur. Yardımcı source tail'i aktarılmaz.

[Gerçek üç sayfalı dosya deneyi](../reports/MULTIPAGE_GENUINE_PROBE.json), [bağımsız teknik inceleme](../reports/MULTIPAGE_REVIEW.md), [milestone](../reports/MULTIPAGE_MILESTONE.json). `program_writer_complete=false`, `full_v1_complete=false`. Alarm/makro entegrasyonu, diğer native türler, tam görünüm/quality, gerçek DIAScreen tarafı, iki ortak pilot ve insan vendor/panel kabulü açık kalır. Önceki clean RAR bu geliştirmeyi içermez.

## Ayrı adres genişletmesi

Bu milestoneın590-test kaynak ve aday kanıtı tarihsel olarak değişmez. Sonraki [radix v2](RADIX_ADDRESSES.md) ile ayrı registered authority ve explicit library/profile upgrade üzerinden X/Y eklenebilir.604-test acceptance önceki native görünüm/vendor kapsamını genişletmez.
