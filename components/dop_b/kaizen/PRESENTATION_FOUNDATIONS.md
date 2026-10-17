# Görünüm alanlarının gerçek sahibi

Gözlem: aynı renk adı farklı nesne türlerinde farklı yüzeye bağlanıyor; font scalar aralığı native okuyucunun kabul aralığıyla aynı değil. Salt aynı dosya uzunluğunda yazma, gerçek okuyucunun alan anlamını kanıtlamıyor.

Kök neden: type/state/reader/compiler/draw zinciri yerine alan ismi ve genişlikten anlam çıkarılması. Bir scalar byte eşit kontrolünden native görünüm kabulü çıkarılamaz.

Karşı görüş: görünüm değişimi bütün sayfalara hemen uygulanabilir. Somut karşı örnekler bunu çürütür: button yüzeyini BgColor ile boyamak yanlış alanı değiştirir; ratio48 okuyucuda100 olur; native16 runtime enum’unu dosyaya taşır; numeric style3’te yüzey rengi kullanılmaz.

Minimum değişiklik: ayrı pinli presentation descriptor ve type-specific alan rolleri; exact font whitelist; canonical ordinary scalar değişimi; independent original-record expectation ve tam gövde restoration. PNG/DIB dönüşümü ayrıca bounded/opaque/same-size primitive olarak ayrılır.

Test: farklı 0/1 renkleri, bütün qualified kind/style kombinasyonları, scalar digit büyümesi/kısalması, eski0/48 korunması, yan numeric/address/caption/resource byte’larının korunması, stale pin/unknown role typed refusal ve bağımsız source-record oracles. [Exact kanıt](../reports/EXISTING_PRESENTATION_FOUNDATION.json), [PNG/DIB](../reports/EXISTING_BACKGROUND_FOUNDATION.json).

Rollback: bu yeni modüller mevcut public branch’i değiştirmez. Kaynak immutable kalır; no-op tam dosya eşitliği ve eski branch testleri korunur. Kabul edilmemiş public birleşim feature olarak açılmaz.

Genellenebilirlik sınırı: seçilen B10 graph/version ve statik primary zincir; DOP-B aile garantisi, DIAScreen, native font/piksel, compiler/runtime ve panel kabulü değildir. Önceki ratio48/100 karşılaştırması compiler’da doğrudan alan etkisini araştırıyordu; yeni okuyucu normalizasyonu ayrı katmandır ve önceki gözlemi üretim eşdeğerliği gibi kullanmayı engeller.
