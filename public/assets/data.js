(() => {
  'use strict';
  const FALLBACK_NEWS = [
    { id:'NEWS-001', category:'THÔNG BÁO', date:'24/09/2026', title:'THÔNG BÁO KHO ACC DELTA FORCE', summary:'Kho acc Reg Skin, acc chế độ OP và các mốc xu tươi được cập nhật theo tình trạng thực tế.', content:'Tạp Hóa Delta Force cập nhật catalogue theo từng đợt hàng. Mở Kho acc và nhắn Zalo để nhận ảnh kho cùng giá chốt mới nhất.', image:'https://cdn.vn.garenanow.com/web/deltaforce/public/df_home/post_generic.jpg', featured:true, pinned:true }
  ];
  const REMOTE_IMAGES = {
    reg:'https://cdn.vn.garenanow.com/web/deltaforce/public/df_home/post_generic.jpg',
    op:'https://web.df.garena.com/02_h5/240923_official_website/vi/pc/gamemode_list_02.jpg',
    xu20:'https://deltaforce.skin/wp-content/uploads/2026/04/cay-xu-sieu-toc-15k-1m-xu-5-scaled.webp',
    xu50:'https://deltaforce.skin/wp-content/uploads/2026/04/cay-box-3x3-4.webp',
    xu100:'https://deltaforce.skin/wp-content/uploads/2026/04/cay-full-phong-ban-can-cu-ngam-9-scaled.webp',
    service:'https://deltaforce.skin/wp-content/uploads/2026/04/cay-xu-sieu-toc-15k-1m-xu-5-scaled.webp'
  };
  const RECOVERED_PRODUCT_IMAGES = {
    "REG-001": "https://cdn.vn.garenanow.com/web/deltaforce/public/df_home/post_generic.jpg",
    "REG-002": "https://cdn.vn.garenanow.com/web/deltaforce/public/df_home/post_generic.jpg",
    "OP-001": "https://web.df.garena.com/02_h5/240923_official_website/vi/pc/gamemode_list_02.jpg",
    "OP-002": "https://web.df.garena.com/02_h5/240923_official_website/vi/pc/gamemode_list_03.jpg",
    "XU-020": "https://deltaforce.skin/wp-content/uploads/2026/04/cay-xu-sieu-toc-15k-1m-xu-5-scaled.webp",
    "XU-050": "https://deltaforce.skin/wp-content/uploads/2026/04/cay-box-3x3-4.webp",
    "XU-100": "https://deltaforce.skin/wp-content/uploads/2026/04/cay-full-phong-ban-can-cu-ngam-9-scaled.webp",
    "SV-001": "https://deltaforce.skin/wp-content/uploads/2026/04/cay-xu-sieu-toc-15k-1m-xu-5-scaled.webp",
    "SV-002": "https://deltaforce.skin/wp-content/uploads/2026/04/cay-box-3x3-4.webp",
    "SV-003": "https://deltaforce.skin/wp-content/uploads/2026/04/cay-full-phong-ban-can-cu-ngam-9-scaled.webp",
    "SV-004": "https://deltaforce.skin/wp-content/uploads/2026/09/phi-thang-thuong-da-sac-5.webp",
    "SV-005": "https://deltaforce.skin/wp-content/uploads/2026/04/vat-pham-gioi-han-binh-xang-luc-day-7.webp"
  };
  const SERVICE_IMAGES = [
    'https://deltaforce.skin/wp-content/uploads/2026/04/cay-xu-sieu-toc-15k-1m-xu-5-scaled.webp',
    'https://deltaforce.skin/wp-content/uploads/2026/04/cay-box-3x3-4.webp',
    'https://deltaforce.skin/wp-content/uploads/2026/04/cay-full-phong-ban-can-cu-ngam-9-scaled.webp',
    'https://deltaforce.skin/wp-content/uploads/2026/09/phi-thang-thuong-da-sac-5.webp',
    'https://deltaforce.skin/wp-content/uploads/2026/04/vat-pham-gioi-han-binh-xang-luc-day-7.webp'
  ];
  const clone = value => JSON.parse(JSON.stringify(value));
  const source = window.DELTA_CATALOG || {};
  function imageFor(item, index=0){
    const image=String(item?.image||'').trim();
    // First use the exact image currently saved by Admin/catalog.
    if(/^https?:\/\//i.test(image) || /^images\/[a-zA-Z0-9._/-]+$/i.test(image)) return image;
    // If that field was cleared, recover the original link from the older working build.
    const recovered=String(RECOVERED_PRODUCT_IMAGES[item?.id]||'').trim();
    if(recovered) return recovered;
    if(item?.category==='service') return SERVICE_IMAGES[index%SERVICE_IMAGES.length];
    return REMOTE_IMAGES[item?.category] || REMOTE_IMAGES.reg;
  }
  function statusFor(item){
    const spec=String(item?.spec||'');
    if(/hết hàng/i.test(spec)) return 'Hết hàng';
    if(/hỏi shop/i.test(spec)) return 'Hỏi shop';
    return 'Còn hàng';
  }
  function build(){
    const settings=source.settings||{};
    const all=(source.products||[]).filter(p=>p && p.active!==0);
    const acc=all.filter(p=>p.category!=='service');
    const svc=all.filter(p=>p.category==='service');
    const categories=(settings.categories||[]).filter(c=>c.id!=='service').map(c=>({...c,kind:'account'}));
    return {
      settings:{shopName:settings.name||'TẠP HÓA',fullName:settings.fullName||'Tạp Hóa Delta Force',zalo:settings.zalo||'0394781498',facebook:String(settings.facebook||'https://www.facebook.com/').trim(),tiktok:String(settings.tiktok||'https://www.tiktok.com/@phi_hng8').trim(),giftTotal:settings.giftTotal==null?300:Number(settings.giftTotal),giftPrice:settings.giftPrice==null?20000:Number(settings.giftPrice),giftNote:settings.giftNote||'Nhập giftcode theo lượt · Báo lại mã sai hoặc đã dùng.',giftHeroImage:String(settings.giftHeroImage||'').trim(),giftHeroType:settings.giftHeroType==='image'?'image':'video',giftHeroVideo:String(settings.giftHeroVideo||'').trim()},
      categories,
      products:acc.map((p,i)=>({id:p.id,category:p.category,name:p.name,price:Number(p.price)||0,status:statusFor(p),image:imageFor(p,i),detailImages:(Array.isArray(p.detailImages)?p.detailImages:[]).filter(x=>typeof x==='string'&&x.trim()).slice(0,20),description:p.description||'',zalo:String(p.zalo||'').trim(),featured:p.featured===undefined?i<4:!!p.featured})),
      services:svc.map((p,i)=>({id:p.id,name:p.name,price:p.spec||((Number(p.price)||0)?money(p.price):'Giá nhắn riêng'),image:imageFor(p,i),detailImages:(Array.isArray(p.detailImages)?p.detailImages:[]).filter(x=>typeof x==='string'&&x.trim()).slice(0,20),description:p.description||'',zalo:String(p.zalo||'').trim(),featured:p.featured===undefined?i<3:!!p.featured})),
      giftcodes:[{id:'GC-300',name:'Nhập giftcode Delta Force',price:settings.giftPrice==null?20000:Number(settings.giftPrice),description:settings.giftNote||'Nhận nhập code theo lượt.'}],
      news:Array.isArray(settings.deltaNews)&&settings.deltaNews.length?clone(settings.deltaNews):clone(FALLBACK_NEWS)
    };
  }
  function money(value){const amount=Number(value)||0;return amount<=0?'LIÊN HỆ':new Intl.NumberFormat('vi-VN',{style:'currency',currency:'VND',maximumFractionDigits:0}).format(amount)}
  function phone(value){return String(value||'').replace(/[^0-9]/g,'')}
  function zaloURL(value){const digits=phone(value||'0394781498');const normalized=digits.startsWith('0')?`84${digits.slice(1)}`:digits;return /^84[35789]\d{8}$/.test(normalized)?`https://zalo.me/${normalized}`:'https://zalo.me/84394781498'}
  function categoryName(catalog,id){return catalog.categories.find(c=>c.id===id)?.name||'Kho acc'}
  const DEFAULT_CATALOG=build();
  window.DF=Object.freeze({STORAGE_KEY:'delta-force-flask-catalog',DEFAULT_CATALOG,clone,load:()=>clone(DEFAULT_CATALOG),save:value=>value,reset:()=>clone(DEFAULT_CATALOG),money,phone,zaloURL,categoryName});
})();
