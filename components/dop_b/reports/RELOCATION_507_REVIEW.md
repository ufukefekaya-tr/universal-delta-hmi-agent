# 507-test kaynağının bağımsız Windows ortam denetimi

Salt-okunur doğrulayıcı gerçek yeni checkout ve kurulu ortamı inceleyerek **PASS** verdi. Source commit `5d7afae3b6b2d351c7922000b550d5add2ed826f`,47 raw hash/revision `4174a7152c9fecfd10cc0a5638ec9d56f2bb21a8c0d4335c0977c362649fc700` committed Git blob'ları, root raporu, gerçek clone ve kopyalanmış test raporuyla birebir eşleşiyor.

Yeni installed runtime'dan bağımsız keşfedilen507 benzersiz test kimliği rapor sırasıyla aynı. Tam logdaki507 ordered ok satırı ve507/0error/0failure/0skip sonucu doğrulandı. [Taşıma kanıtı](relocation_verification.json), [testler](relocation_tests.json), tam log (tarihsel yerel kanıt; genel pakete dahil değil: `relocation_tests.log`), kurulum logu (tarihsel yerel kanıt; genel pakete dahil değil: `relocation_install.log`).

Gerçek ayrı .git içinde origin ve alternates yok;691 ortak Git object dosyasının her biri kaynak checkout dosyasından farklı fiziksel dosya. Yeni venv prefix/executable/editable direct_url/module yeni konuma çözülüyor; caller checkout dışında. PYTHONHOME/PYTHONPATH ve eski source sys.path/sanitized PATH'te yok; include-system-site-packages=false. Conditional lock'un30 aktif pin'i kurulu sürümlerle eşleşti; fresh pip check0. Dört kayıt host-neutral. Yeni ortamda native DPS/DPA veya vendor asset yok.

Önemli açık bulgu0. Denetmen dosya/state/staging/commit/UI değişikliği ve yeniden tam suite çalıştırması yapmadı. Bu aynı fiziksel Windows host'unda yeni konum/yeni kurulum kabulüdür. Linux/macOS, ikinci fiziksel PC, vendor/panel veya fullV1 kabulü değildir; sonraki kaynak değişiklikleri bu kabulü otomatik devralmaz.
