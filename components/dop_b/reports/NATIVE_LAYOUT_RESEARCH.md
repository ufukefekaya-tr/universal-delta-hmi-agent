# Layout ve görünüm — kaynak gözlemleri

Bu inceleme salt okunurdur. Vendor dosyaları, görseller, başka makinenin tagları ve uygulama kodu repoya alınmadı. Gözlem enum/özellik qualification, native görsel PASS veya seçilmiş hedefin üretim kabulü değildir. Public gerçek native üretim kapalıdır.

## Güncel iki değişiklik holdout'u

Installed FullDemo kaynağı SHA `fc079f74ed9b34e2e698b0c65c95c4f914983594f658cadc72e1ee4d97493ed5`, model `268502784` (DOP-107WV), editor `6.0.00205.8268`; seçilmiş DOP-110IS profili değildir. Kaynak okuyucu iki holdout'u native modülü SHA `25e21d0ae07ff344d7165d1639412b314d56a0edbfaca75106052fee10dacb8b` üzerinde yeniden çalıştırdı:

| Tetikleyici | Kontrollü değişiklik | Bellekte aday SHA |
|---|---|---|
| Screen20/object7/State0 font 22→24 | Yalnız section39/record6 `FontSize0` | `0c88b5261519447f980cc3e05166ce62559280d5c131d9cec1324edafb100658` |
| Screen20/object5 hedef ID2/Meter→20/Base | Yalnız section33/records38–39 `GoToScreenID` ve `GoToScreenName` | `4793cdf51359c019e0ed35f4911c3e1276b527d7444f7c53eadde18f9b764a58` |

Her ikisinde yeniden okuma, empty-op bütün-byte eşitliği ve kaynak değişmezliği geçti. Header, prefix, kaydedilmiş thumbnail, tail ve diğer kayıtlar byte eşit kaldı. Hiçbir aday dosya kaydedilmedi; vendor render/compile ve panel işlemi yapılmadı. Bu native yardımcıların dar kayıpsız mutasyon kanıtıdır; MCP public production gate'ini açmaz.

## Renk ve font sınırı

FullDemo'nun kendi kaydettiği thumbnail'da State.FontColor `15637312` (`0xEE9B40`), aynı konumda RGB `(64,155,238)` 36 piksel ile eşleşti. `FgColor=8404992` (`0x804000`), RGB `(0,64,128)` 3 piksel ile eşleşti. Bu, gözlenmiş 24-bit COLORREF `R | G<<8 | B<<16` sözleşmesini destekler. İlk özgün sentetik fixture'ın `rgb24` sözleşmesi ayrı kalır; encoding tahmin edilmez.

[Public Dosificador kaynağı](https://github.com/ismaelfari1996/hmi-simulacion-dosificador), commit `aa8684c51dcd4372d6dc7d274d7cf7a51a7d94d1`, `.dps` SHA `07d90a3900cb86e994b55a467f594809e4ffe1e0681f329d205ff26b3b688f90`; model DOP-B03E211, editor `4.00.07.04`. Kaydedilmiş thumbnail'da `FgColor=0xE89432` için RGB `(50,148,232)` 1.755 piksel; maintained Type1/SubType4 nesnesinin `FgColor=255` değeri için 115 kırmızı piksel görüldü. Yanlış B modeli/editorü olduğu için DOP-B07S411/DOPSoft2 kabulü değildir. GPL kaynak/ikonlar ve native dosya dağıtılmadı; sentetik maintained enum2 gerçek enum4 qualification'ı olarak sunulmaz.

Observed temel font alanı State.FontSize0; State.FontRatio0=100, ASCII FontName0 ve exact style companions dar scalar sözleşmesidir. Native font değerinin CSS pixel karşılığı, Türkçe glyph rendering, italic/underline ve gerçek font fallback açık kalır. FontSize ile FontSize0 sessizce birbirinin yerine kullanılmaz.

## Toplu gözlem sınırı ve karşı örnekler

22 kurulu dosya taramasının tam kaynak manifesti saklanmadı. Aşağıdakiler aggregate field-presence gözlemidir; 22 ayrı artifact-bound qualification olarak kullanılamaz:

- 9.293 State'te FontSize0/FontRatio0; iki ratio50 örneği, 914 scalar GoToScreenName ve 10 non-ASCII dar isim. CP936 isimler ile UTF-16 sayfa isimleri tutarsız olabiliyor; ASCII dışı navigation companion encoding'i kapalıdır.
- 2.084 Element.Order alanı; çoğu sıfır. Native `Order` ile stream sırasının ilişki anlamı kalibre edilmedi. [DOPSoft kılavuzu](https://filecenter.deltaww.com/Products/download/06/060302/Manual/DELTA_IA-HMI_DOPSoft_UM_EN_20211230.pdf) section2.2.2.11 creation order'ın katmanla ilişkisini anlatır; native `Order` enum/stream eşitliği kanıtı vermez.
- UsePictureCoord=0 bulunan State'lerde PictureOffset/PIB Name/Picture Name yine bulunur; sıfır flag görüntü yokluğunun kanıtı değildir.
- Appearance alanları kind prefix'i taşıyabilir: NumBgOpacity, BtnPictureStretch, FieldFontSize, KPBkgndColor, BtnTransColor. nAngle, CutDraw, Visible*, UnitTextLenN, TitleHeight ve bFreeze de ayrı companion hesabı gerektirir. Alan adından davranış çıkarılmaz; bilinmeyen baseline reddedilir.
- 1.505 UnitTextLenN kaydı decimal byte length + NUL dahil UTF-16LE + CRLF düzeninde görüldü. Mevcut parser/semantic compiler bu unit kaydını qualify etmez; unit sahipliği/yönü/konumu açıktır.

SYNTHETIC layout fixture'ındaki text Type77 ve indicator Type78 tamamen özgün test değerleridir. Gerçek vendor nesne enumları değildir. Yeni sayfa baseline'ı yalnız VER16/ID/wTextLen/DocSizeX-Y/PanelSizeX-Y tam yedi alan + empty Aux şekliyle sınırlıdır; vendor sayfalardaki diğer alanlar silinmez, bu clone yolu reddedilir.
