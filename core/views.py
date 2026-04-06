from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import AuctionItem, Bid, Notification, CustomUser
from .forms import CustomUserCreationForm, AuctionItemForm, EmailAuthenticationForm
from decimal import Decimal
import random
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
import razorpay

def home(request):
    active_auctions = AuctionItem.objects.filter(is_active=True, end_time__gt=timezone.now()).order_by('end_time')
    return render(request, 'home.html', {'auctions': active_auctions})

def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            try:
                login_url = request.build_absolute_uri(reverse('login'))
                html_message = render_to_string('emails/welcome_email.html', {
                    'user': user,
                    'login_url': login_url
                })
                send_mail(
                    'Welcome to bidXchanger!',
                    f'Welcome to bidXchanger, {user.username}! Thank you for joining.',
                    settings.EMAIL_HOST_USER,
                    [user.email],
                    fail_silently=False,
                    html_message=html_message
                )
            except Exception as e:
                print(f"Failed to send welcome email: {e}")

            messages.success(request, f"Registration successful. Please log in with your email and password.")
            return redirect('login')
    else:
        form = CustomUserCreationForm()
    return render(request, 'register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = EmailAuthenticationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data.get('email')
            password = form.cleaned_data.get('password')
            user = authenticate(request, email=email, password=password)
            if user is not None:
                otp = str(random.randint(100000, 999999))
                try:
                    html_message = render_to_string('emails/otp_email.html', {'otp': otp})
                    send_mail(
                        'Your bidXchanger Secure Login OTP',
                        f'Your verification code is: {otp}',
                        settings.EMAIL_HOST_USER,
                        [user.email],
                        fail_silently=False,
                        html_message=html_message
                    )
                except Exception as e:
                    print(f"Failed to send email: {e}")
                    
                print(f"DEBUG - OTP for {user.email}: {otp}")
                
                request.session['pre_otp_user_id'] = user.id
                request.session['otp_code'] = otp
                messages.success(request, "An OTP has been sent to your email address.")
                return redirect('verify_otp')
            else:
                messages.error(request, "Invalid email or password.")
    else:
        form = EmailAuthenticationForm()
    return render(request, 'login.html', {'form': form})

def verify_otp(request):
    user_id = request.session.get('pre_otp_user_id')
    otp_code = request.session.get('otp_code')

    if not user_id or not otp_code:
        messages.error(request, "No pending login session found. Please log in again.")
        return redirect('login')

    if request.method == 'POST':
        entered_otp = request.POST.get('otp')
        if entered_otp == otp_code:
            try:
                user = CustomUser.objects.get(id=user_id)
                login(request, user, backend='core.backends.EmailBackend')
                del request.session['pre_otp_user_id']
                del request.session['otp_code']
                messages.success(request, f"Welcome back, {user.username}!")
                return redirect('dashboard')
            except CustomUser.DoesNotExist:
                messages.error(request, "User doesn't exist anymore.")
                return redirect('login')
        else:
            messages.error(request, "Invalid OTP. Please check your email and try again.")
            
    return render(request, 'verify_otp.html')

def logout_view(request):
    logout(request)
    messages.info(request, "You have successfully logged out.")
    return redirect('home')

@login_required
def dashboard(request):
    if request.user.is_seller:
        items = AuctionItem.objects.filter(seller=request.user)
        from django.db.models import Sum
        total_revenue = items.filter(is_paid=True).aggregate(Sum('current_price'))['current_price__sum'] or 0
        active_items = items.filter(end_time__gt=timezone.now()).count()
        
        context = {
            'items': items,
            'role': 'seller',
            'total_revenue': total_revenue,
            'total_items': items.count(),
            'active_items': active_items,
            'now': timezone.now(),
        }
        return render(request, 'dashboard.html', context)
        
    elif request.user.is_buyer:
        bids = Bid.objects.filter(bidder=request.user)
        ended_items = AuctionItem.objects.filter(id__in=bids.values('auction_id'), end_time__lt=timezone.now())
        won_items = [item for item in ended_items if item.winner == request.user]
        total_spent = sum(item.current_price for item in won_items if item.is_paid)
        
        context = {
            'bids': bids,
            'role': 'buyer',
            'won_items': won_items,
            'total_spent': total_spent,
            'total_bids': bids.count(),
            'now': timezone.now(),
        }
        return render(request, 'dashboard.html', context)
        
    else:
        return render(request, 'dashboard.html', {'role': 'user'})

@login_required
def create_auction(request):
    if not request.user.is_seller:
        messages.error(request, "Only sellers can create auctions.")
        return redirect('home')
        
    if request.method == 'POST':
        form = AuctionItemForm(request.POST, request.FILES)
        if form.is_valid():
            item = form.save(commit=False)
            item.seller = request.user
            item.save()
            messages.success(request, "Auction created successfully!")
            return redirect('dashboard')
    else:
        form = AuctionItemForm()
    return render(request, 'create_auction.html', {'form': form})

def auction_detail(request, item_id):
    item = get_object_or_404(AuctionItem, id=item_id)
    bids = item.bids.all().order_by('-amount')
    now = timezone.now()
    return render(request, 'auction_detail.html', {'item': item, 'bids': bids, 'now': now})

@login_required
def place_bid(request, item_id):
    if not request.user.is_buyer:
        messages.error(request, "Only buyers can place bids.")
        return redirect('auction_detail', item_id=item_id)
        
    item = get_object_or_404(AuctionItem, id=item_id)
    
    if item.end_time < timezone.now():
        messages.error(request, "This auction has ended.")
        return redirect('auction_detail', item_id=item_id)
        
    if request.method == 'POST':
        try:
            bid_amount = Decimal(request.POST.get('amount'))
            if bid_amount <= item.current_price:
                messages.error(request, "Bid must be higher than the current highest bid.")
            else:
                Bid.objects.create(auction=item, bidder=request.user, amount=bid_amount)
                item.current_price = bid_amount
                item.save()
                
                Notification.objects.create(
                    user=item.seller,
                    message=f"New bid of ₹{bid_amount} placed on your item '{item.title}'."
                )
                
                messages.success(request, "Bid placed successfully!")
        except Exception as e:
            messages.error(request, "Invalid bid amount.")
            
    return redirect('auction_detail', item_id=item_id)

def about(request):
    return render(request, 'about.html')

@login_required
def checkout(request, item_id):
    if not request.user.is_buyer:
        messages.error(request, "Only buyers can make payments.")
        return redirect('dashboard')
        
    from .models import Payment
    item = get_object_or_404(AuctionItem, id=item_id)
    
    if item.end_time > timezone.now():
        messages.error(request, "This auction has not ended yet.")
        return redirect('auction_detail', item_id=item_id)
        
    if item.winner != request.user:
        messages.error(request, "You did not win this auction.")
        return redirect('dashboard')
        
    if item.is_paid:
        messages.info(request, "This item has already been paid for.")
        return redirect('dashboard')
        
    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

    if request.method == 'POST':
        # Verify payment signature
        razorpay_payment_id = request.POST.get('razorpay_payment_id')
        razorpay_order_id = request.POST.get('razorpay_order_id')
        razorpay_signature = request.POST.get('razorpay_signature')
        
        try:
            client.utility.verify_payment_signature({
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            })
            
            # Payment successful, save state
            Payment.objects.create(
                auction=item,
                user=request.user,
                amount=item.current_price,
                status='completed'
            )
            item.is_paid = True
            item.save()
            messages.success(request, f"Payment of ₹{item.current_price} successful! The seller will be notified.")
            return redirect('dashboard')
        except razorpay.errors.SignatureVerificationError:
            messages.error(request, "Payment verification failed. Please try again.")
            return redirect('checkout', item_id=item.id)
            
    # GET Request: Create a Razorpay Order
    amount_in_paise = int(item.current_price * 100)
    data = {
        "amount": amount_in_paise,
        "currency": "INR",
        "receipt": f"order_rcptid_{item.id}"
    }
    try:
        payment_order = client.order.create(data=data)
        order_id = payment_order['id']
    except Exception as e:
        messages.error(request, "Error initializing Razorpay payment. Check API credentials.")
        return redirect('dashboard')

    context = {
        'item': item,
        'razorpay_order_id': order_id,
        'razorpay_key': settings.RAZORPAY_KEY_ID,
        'amount_in_paise': amount_in_paise
    }
    return render(request, 'checkout.html', context)

@login_required
def cancel_auction(request, item_id):
    item = get_object_or_404(AuctionItem, id=item_id)
    if request.user != item.seller:
        messages.error(request, "You can only cancel your own items.")
        return redirect('dashboard')
    
    if item.end_time < timezone.now():
        messages.error(request, "Cannot cancel an ended auction.")
        return redirect('dashboard')

    item.is_active = False
    item.save()

    # Notify unique bidders
    bidders = set([bid.bidder for bid in item.bids.all()])
    for bidder in bidders:
        Notification.objects.create(
            user=bidder,
            message=f"The auction for '{item.title}' has been cancelled by the seller."
        )

    messages.success(request, "Auction cancelled successfully.")
    return redirect('dashboard')

@login_required
def delete_auction(request, item_id):
    item = get_object_or_404(AuctionItem, id=item_id)
    if request.user != item.seller:
        messages.error(request, "You can only delete your own items.")
        return redirect('dashboard')
        
    if item.is_active:
        messages.error(request, "You can only delete cancelled or ended items.")
        return redirect('dashboard')
        
    item.delete()
    messages.success(request, "Auction item permanently deleted.")
    return redirect('dashboard')

@login_required
def withdraw_bid(request, bid_id):
    bid = get_object_or_404(Bid, id=bid_id)
    if request.user != bid.bidder:
        messages.error(request, "You can only withdraw your own bids.")
        return redirect('dashboard')
        
    item = bid.auction
    if item.end_time < timezone.now():
        messages.error(request, "Cannot withdraw bids from ended auctions.")
        return redirect('dashboard')
        
    bid.delete()
    
    # Recalculate highest bid
    highest_bid = item.bids.order_by('-amount').first()
    if highest_bid:
        item.current_price = highest_bid.amount
    else:
        item.current_price = item.starting_bid
    item.save()
    
    messages.success(request, "Bid successfully withdrawn.")
    return redirect('dashboard')
