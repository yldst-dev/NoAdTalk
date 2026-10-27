#import <Cocoa/Cocoa.h>

@interface BDView : NSView @end
@implementation BDView @end
@interface BDButton : NSButton @end
@implementation BDButton @end
@interface BDTextField : NSTextField @end
@implementation BDTextField @end
@interface BLKButtonCell : NSButtonCell @end
@implementation BLKButtonCell @end
@interface BLKCircleTextFieldCell : NSTextFieldCell @end
@implementation BLKCircleTextFieldCell @end
@interface BLKMenuItem : NSMenuItem @end
@implementation BLKMenuItem @end

@interface FSMainViewController : NSObject
@property(nonatomic, weak) NSLayoutConstraint *advertiseContainerHeightConstraint;
@property(nonatomic, weak) NSLayoutConstraint *adSeparatorHeightConstraint;
@property(nonatomic, weak) NSView *advertiseContainerView;
@property(nonatomic, weak) NSView *contentView;
@property(nonatomic, strong) NSView *view;
@end

@implementation FSMainViewController
- (void)setValue:(id)value forUndefinedKey:(NSString *)key {}
@end

int main(int argc, const char **argv) {
    @autoreleasepool {
        if (argc != 2) return 2;
        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyProhibited];
        NSBundle *bundle = [NSBundle bundleWithPath:[NSString stringWithUTF8String:argv[1]]];
        NSNib *nib = [[NSNib alloc] initWithNibNamed:@"FSMainViewController" bundle:bundle];
        FSMainViewController *owner = [FSMainViewController new];
        NSArray *objects = nil;
        if (![nib instantiateWithOwner:owner topLevelObjects:&objects]) return 3;
        NSLayoutConstraint *height = owner.advertiseContainerHeightConstraint;
        NSView *ad = height.firstItem;
        if (![height isKindOfClass:[NSLayoutConstraint class]] || ![ad isKindOfClass:[NSView class]] || !owner.contentView || !owner.view) return 4;
        [owner.view layoutSubtreeIfNeeded];
        printf("%.0f %.0f %d %.0f %.0f %d\n", height.constant, owner.adSeparatorHeightConstraint.constant, ad.hidden, owner.contentView.frame.size.height, ad.frame.size.height, owner.advertiseContainerView != nil);
    }
    return 0;
}
