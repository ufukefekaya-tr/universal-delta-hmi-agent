# Referans nesneleri çıktıya taşımadan üretim

Gözlem: Kaynağa yeni kontrol ekleyen yazıcı, kaynaktaki boş adresli referans nesnelerini de koruyordu. Böyle bir dosya temiz yeni ekran değildir. Donor koruma testi PASS olsa bile adayın bütün nesnelerinin tasarıma ait olduğunu kanıtlamaz.

Kök neden: üretim hedefi ile tür/özellik kütüphanesi aynı dosya kabul edilmişti. Düzeltme ayrı, sıfır-owner hedef ve değişmez tam altı-owner kütüphane kullanmaktır. Global/sayfa/kaynak lineage karşılaştırması, hedefin kendi byte'larının korunması ve yalnız yeni owner'ların eklenmesi gerekir.

Karşı bulgu B1: Yardımcı kütüphane profili registry'nin typed doğrulamasını atlıyordu. Yeniden SHA'lanan eksik resolution ham KeyError verdi; eksik id oturum açıldıktan sonra patladı. Ortak profil kapısı servis ve calibration helper'da ilk dereference önüne taşındı. Root23 eksik/yanlış-tip varyantını iki girişte sınar; oturum ve çıktı oluşmamalıdır. Bağımsız yeniden inceleme kapanış kanıtıdır.

Kaynak farkı: Kontrollerin ilk vendor kaydı yalnız owned boş Tag bağlantısını0→1 olarak başlatmıştı. Tam framed extent belirlenmeden bu geçiş uygulanamaz; resim veya SRAM içindeki benzer yazı bölüm değildir. Yeni adaydan altı owner çıkarıp yalnız bu geçişi tersine çevirmek bütün hedef gövdesini byte-exact geri vermelidir.

Rollback: Yeni aday/calibration revision'ı bırakılır, değişmemiş hedef ve kütüphane yeniden açılır. Önceki append modu ayrı kalır. Genel ders, aynı native kayıtların her model/driver/adres için çalıştığı iddiası değildir; vendor/runtime/panel kabulü dosya SHA'sına bağlı kalır.
