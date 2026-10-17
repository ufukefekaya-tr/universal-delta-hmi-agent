# Yeni ajan başlangıcı

AGENTS.md → SYSTEM_PROMPT.md → INDEX.md → workflow/goals ve ilgili checkpoint'i okuyun. Önce `delta_catalog` ile gerçek backend durumunu alın. Projenin hedef ailesi açıkça belirlenmiş olmalı. İki ailenin registry/çalışma/state dosyalarını paylaşmayın.

Kaynak profil capability'sini okuyun; kullanıcıdan mevcut kayıtta bulunan bilgiyi tekrar istemeyin. Belirsiz kritik model/adres/izin bilgisini tahmin etmeyin. Kaynak dosyayı hash ile dondurun. Tasarım, typed bindings, buton davranışı, sayısal limitler ve feedback/stale sözleşmesi hazırlayın. Önizleme ve bağımsız incelemelerden sonra backend'in onaylı üretim yolunu kullanın. Tek dosya üretimini tamamlanma saymayın; kaydedilmiş dosyayı yeniden inceleyin.

Kurulum eksiğinde pinli bootstrap yolunu kullanın. GUI/IDE açmayın. Fiziksel panel veya PLC bulunmaması yazılım indirilerek çözülmez. Vendor/physical kanıtını ayrı açık iş olarak bırakın. Hata çıktısını gizlemeyin; family fallback yapmayın.

Makine kaynakları genel repoya alınmaz. Repo yalnız araçları, tarafsız sözleşmeleri ve uygun paylaşım izni bulunan testleri içerir. Görev sonunda exact sonuç, test sınırı, açık işler, manifest ve scoped yerel commit üretin.
