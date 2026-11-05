"""প্রথমবার চালালে ক্যাটাগরি + সাইট সেটিংস তৈরি করে (শুধু ফাঁকা DB তে)।
`--products` দিলে ছবি ছাড়া কয়েকটা ডেমো প্রোডাক্টও বানায় (টেস্টের জন্য; পরে admin থেকে মুছে দিন)।"""
from django.core.management.base import BaseCommand

from store.models import Category, Coupon, Product, ProductVariant, SiteSetting

CATEGORIES = [
    ("electronics", "ইলেকট্রনিক্স"), ("mobile-accessories", "মোবাইল ও অ্যাক্সেসরিজ"), ("home-kitchen", "ঘর ও রান্নাঘর"),
    ("fashion", "ফ্যাশন"), ("beauty-care", "বিউটি ও পার্সোনাল কেয়ার"), ("grocery", "গ্রোসারি"),
    ("sports-fitness", "স্পোর্টস ও ফিটনেস"), ("toys-kids", "খেলনা ও বাচ্চাদের পণ্য"), ("books-stationery", "বই ও স্টেশনারি"),
    ("combo", "কম্বো অফার"),
]
# আগের (শুধু পোশাকের) ডিফল্ট ক্যাটাগরি — এগুলোতে কোনো প্রোডাক্ট না থাকলে নতুন সাধারণ ক্যাটাগরি দিয়ে বদলে দেওয়া হয়
OLD_CLOTHING_SLUGS = {"shirt", "polo", "dropshoulder", "pants", "punjabi", "combo", "jersey"}

DEMO = [
    ("DEMO-EL01", "ওয়্যারলেস ব্লুটুথ ইয়ারবাড", "electronics", 1250, 1650, [("Free", "ব্ল্যাক", "#111111"), ("Free", "হোয়াইট", "#f2f2f2")]),
    ("DEMO-HK01", "স্টেইনলেস স্টিল ওয়াটার বোতল", "home-kitchen", 480, 650, [("500ml", "", ""), ("750ml", "", "")]),
    ("DEMO-MA01", "ফাস্ট চার্জিং ইউএসবি-সি কেবল", "mobile-accessories", 220, None, [("1m", "", ""), ("2m", "", "")]),
    ("DEMO-BC01", "ফেস ওয়াশ (১০০ মি.লি.)", "beauty-care", 290, 350, [("Free", "", "")]),
]


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--products", action="store_true")

    def handle(self, *args, **opts):
        SiteSetting.load()
        existing = set(Category.objects.values_list("slug", flat=True))
        # আগের পোশাক-ভিত্তিক ডিফল্ট ক্যাটাগরি, কোনো প্রোডাক্ট ছাড়া → বদলে দাও
        if existing and existing <= OLD_CLOTHING_SLUGS and not Product.objects.filter(category__slug__in=existing).exists():
            Category.objects.filter(slug__in=existing).delete()
            existing = set()
            self.stdout.write("Old clothing-only default categories removed.")
        if not existing:
            for i, (slug, name) in enumerate(CATEGORIES):
                Category.objects.create(slug=slug, name=name, position=i)
            self.stdout.write("Categories created.")
        if opts["products"]:
            for code, name, cat, price, old, variants in DEMO:
                if Product.objects.filter(code=code).exists():
                    continue
                p = Product.objects.create(
                    code=code, name=name, category=Category.objects.filter(slug=cat).first(), price=price, old_price=old,
                    is_featured=True, description="এটি একটি ডেমো প্রোডাক্ট। Admin panel থেকে মুছে আসল প্রোডাক্ট যোগ করুন।",
                    fabric="", fit="", care="",
                )
                for size, color, hexv in variants:
                    ProductVariant.objects.create(product=p, size=size, color=color, color_hex=hexv, stock=20)
            Coupon.objects.get_or_create(code="WELCOME10", defaults={"discount_type": "percent", "value": 10, "min_order": 500})
            self.stdout.write("Demo products + WELCOME10 coupon created.")
