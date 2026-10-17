# Ayrı donor sorumluluğu ve tam graph kabulü

Gözlem: Aynı B10 vendor yazılımında sıradan yeni sayfa kaydı HMIPortNr0 değerini değiştirdi; eski numeric owner font oranlarını normalleştirdi. Yeni page ScreenAction alanı tutarlı kaydedilse de rastgele negatif değerdir. Kaynağın aynı model olması bütün byte'ları güvenle klonlamaya yetmez.

Kök neden: Dosya save metadata'sı, yeni typed owner'lar ve eski driver/visual kayıtları aynı gövdede bulunur. Monolitik donor klonlama bu ayrı sahiplikleri birleştirir. Position-based zip kontrolü final page/owner sayısının bir bölümünü atlayabilir.

Karşı görüş: Vendor yeniden kaydı tek authority sayıp eski numeric source'u yenilemek daha kolaydır. Bu driver değişikliğini meşrulaştırır ve kaynak exactness'ını kaybettirir. Property hash'i veya testlerin uzlaşması bu riski kapatmaz.

Minimum değişiklik: Blank hedef globals/resources sahibi; orijinal altı kontrol library değişmez; auxiliary kaynak yalnız ayrı exact page/owner pin'leri sağlar. Yeni ordinary sayfaya static proven Action0 yazılır; original Action exact kalır. Tam declared graph, native masked-record verification ve ayrı IR→whole-body expectation birlikte kullanılır.

Test: Gerçek vendor pair'lerinde eklenen extent ve yalnız enumerated save farkları geri alınınca bütün önceki body exact geri gelir. Üç sayfalı gerçek9SDK adayında13owner, doğru hedef/name, command type ve indicator read-only/state0/1 korunur. Donor poisoned globals, yanlış typed metadata, owned/unmanaged tamper ve source/authority freshness negatifleri sınanır. Denetmenin M1 finding'i op/kind/property-key list/object ham exception'ları typed reject'e dönüştürmüş ve altı tekrar testiyle kapanmıştır.

Rollback: Native kaynaklar read-only, candidate ayrı yeni dosyadır; eski committed emitter ve immutable clean RAR korunur. Kaynak/property/authority değişirse yeniden kalibrasyon gerekir; flags açılarak devam edilmez.

Genellenebilirlik sınırı: Bu yöntem kaynak koruması dersidir. B10 stored-file kanıtı diğer model, editor, driver, native pixels, PLC communication-loss veya panel çalışmasını doğrulamaz. Dinamik izin/quality ve gerçek alarm/history testleri ayrı kalır.
