# Workflow ve geçiş kapıları

1. **Kaynak dondurma:** iki aile kaynağı, sürüm, hash, lisans ve araç listesi bulunur. Kaynakların başka görevlere ait dosyaları değiştirilmez.
2. **Özellik envanteri:** her tarihsel işlev `FEATURE_MIGRATION.json` satırına bağlanır. İptal edilen deneme, sadece kütüphanede görülen işlev ve doğrulanmış özellik ayrılır.
3. **Bağımsız backend üretimi:** DOP-B mevcut sürümü korunur; DIAScreen ayrı repo sahibi tarafından genelleştirilir. Ortak çatı bu depolara yazmaz.
4. **Sözleşme:** her backend sabit giriş noktası, araç şeması, profil/aile kimliği, yetki/onay ve paket manifesti teslim eder. Eksik backend disabled kalır.
5. **İzolasyon:** kurulum, workspace, registry ve state ayrılır; ters aile, eski kimlik, kaynak drift ve süreç arızası negatif testleri geçer.
6. **Gerçek MCP testi:** araç keşfinin yanı sıra kaynak açma, plan, önizleme, doğrulama, izinli uygulama, ayrı kayıt ve payload karşılaştırması yapılır. Sentetik fixture açıkça etiketlenir.
7. **Aktarım kontrolü:** her eski dosya aracı/özellik yeni uygulama ve testine ya da gerekçeli kapsam dışı kaydına bağlanır. Yeni backend'in ek araçları sessizce filtrelenemez; haritalama yapılmadan birleşik kabul kapanmaz.
8. **Bağımsız son denetim:** uygulayıcıdan ayrı denetmen kaynak listesiyle uygulamayı karşılaştırır, atlanan işlev ve müşteri izi arar. Kritik/önemli bulgular kapanır.
9. **Paket ve commit:** manifest, kurulum/taşıma sonuçları, açık işler ve hashler birlikte dondurulur; yalnız görev dosyaları yerel commit edilir. Push yapılmaz.
10. **Vendor/fiziksel kabul:** insanın exact dosya/model/senaryo kanıtı ayrı kaydedilir. Bu kabul olmadan offline sonuç yükseltilmez.

Yeni bir makine tasarımı ayrıca iki sıralı estetik denetim ve önizleme onayı ister. Bu altyapı işinde makine tasarımı üretilmediği için estetik başarı iddiası yoktur.
