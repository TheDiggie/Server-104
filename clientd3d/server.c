// Meridian 59, Copyright 1994-2012 Andrew Kirmse and Chris Kirmse.
// All rights reserved.
//
// This software is distributed under a license that is described in
// the LICENSE file that accompanies it.
//
// Meridian is a registered trademark.
/*
 * server.c:  Handle messages from the server.
 *
 * The main function here searches through the table of message handlers and calls
 * the one that matches.  There are separate tables for login and game modes, since
 * the protocol is completely different in these modes.
 *
 * The message handlers parse the message and call appropriate client functions.
 * There are some utility parsing functions starting with the word "Extract".
 */

#include "client.h"

extern Bool            gD3DRedrawAll;

static handler_struct connecting_handler_table[] = {
{ 0, NULL},   // must end table this way
};

static handler_struct login_handler_table[] = {
{ AP_GETLOGIN,          HandleGetLogin },
{ AP_LOGINOK,           HandleLoginOk },
{ AP_LOGINFAILED,       HandleLoginFailed },
{ AP_GAME,              HandleEnterGame },
{ AP_ADMIN,             HandleEnterAdmin },
{ AP_GETCHOICE,         HandleGetChoice },
{ AP_GETCLIENT,         HandleGetClient },
{ AP_ACCOUNTUSED,       HandleAccountUsed },
{ AP_TOOMANYLOGINS,     HandleTooManyLogins },
{ AP_TIMEOUT,           HandleTimeout },
{ AP_CREDITS,           HandleCredits },
{ AP_DOWNLOAD,          HandleDownload },
{ AP_NOCREDITS,         HandleNoCredits },
{ AP_MESSAGE,           HandleLoginErrorMsg },
{ AP_RESYNC,            HandleLoginResync },
{ AP_DELETERSC,         HandleDeleteRsc },
{ AP_DELETEALLRSC,      HandleDeleteAllRsc },
{ AP_NOCHARACTERS,      HandleNoCharacters },
{ AP_CLIENT_PATCH,      HandleClientPatch },
{ 0, NULL},   // must end table this way
};

static handler_struct game_handler_table[] = {
{ BP_MOVE,              HandleMove },
{ BP_TURN,              HandleTurn },
{ BP_CREATE,            HandleCreate },
{ BP_REMOVE,            HandleRemove },
{ BP_CHANGE,            HandleChange },
{ BP_CHANGE_FLAGS,      HandleChangeFlags },
{ BP_LOOK,              HandleLook },
{ BP_LOOK_SPELL,        HandleLookSpell },
{ BP_LOOK_SKILL,        HandleLookSkill },
{ BP_USE,               HandleUse },
{ BP_UNUSE,             HandleUnuse },
{ BP_USE_LIST,          HandleUseList },
{ BP_SAID,              HandleSaid },
{ BP_OBJECT_CONTENTS,   HandleObjectContents },
{ BP_BUY_LIST,          HandleBuyList },
{ BP_WITHDRAWAL_LIST,   HandleWithdrawalList },
{ BP_INVENTORY_ADD,     HandleInventoryAdd },
{ BP_INVENTORY_REMOVE,  HandleInventoryRemove },
{ BP_PLAYER_ADD,        HandleAddPlayer },
{ BP_PLAYER_REMOVE,     HandleRemovePlayer },
{ BP_MESSAGE,           HandleStringMessage },
{ BP_SYS_MESSAGE,       HandleSysMessage },
{ BP_ECHO_PING,         HandleEchoPing },
{ BP_ECHO_UDP_PING,     HandleEchoUDPPing },
{ BP_OFFER_CANCELED,    HandleOfferCanceled },
{ BP_OFFER,             HandleOffer },
{ BP_OFFERED,           HandleOffered },
{ BP_COUNTEROFFER,      HandleCounteroffer },
{ BP_COUNTEROFFERED,    HandleCounteroffered },
{ BP_QUIT,              HandleQuit },
{ BP_RESYNC,            HandleGameResync },
{ BP_INVALIDATE_DATA,   HandleInvalidateData },
{ BP_INVENTORY,         HandleInventory },
{ BP_PLAYER,            HandlePlayer },
{ BP_ROOM_CONTENTS,     HandleRoomContents },
{ BP_ROOM_CONTENTS_FLAGS, HandleRoomContentsFlags },
{ BP_PLAYERS,           HandlePlayers },
{ BP_WAIT,              HandleWait },
{ BP_UNWAIT,            HandleUnwait },
{ BP_PLAY_WAVE,         HandlePlayWave },
{ BP_PLAY_MIDI,         HandlePlayMidi },
{ BP_PLAY_MUSIC,        HandlePlayMusic },
{ BP_STOP_WAVE,         HandleStopWave },
{ BP_EFFECT,            HandleEffect },
{ BP_MOVEMENT_SPEED,    HandleMovementSpeed },
{ BP_SHOOT,             HandleShoot },
{ BP_RADIUS_SHOOT,      HandleRadiusShoot },
{ BP_LIGHT_AMBIENT,     HandleLightAmbient },
{ BP_LIGHT_PLAYER,      HandleLightPlayer },
{ BP_LIGHT_SHADING,     HandleLightShading },
{ BP_BACKGROUND,        HandleBackground },
{ BP_LOAD_MODULE,       HandleLoadModule },
{ BP_UNLOAD_MODULE,     HandleUnloadModule },
{ BP_CHANGE_RESOURCE,   HandleChangeResource },
{ BP_PLAYER_OVERLAY,    HandlePlayerOverlay },
{ BP_SECTOR_MOVE,       HandleSectorMove },
{ BP_WALL_ANIMATE,      HandleWallAnimate },
{ BP_SECTOR_ANIMATE,    HandleSectorAnimate },
{ BP_SECTOR_CHANGE,     HandleSectorChange },
{ BP_ADD_BG_OVERLAY,    HandleAddBackgroundOverlay },
{ BP_REMOVE_BG_OVERLAY, HandleRemoveBackgroundOverlay },
{ BP_CHANGE_BG_OVERLAY, HandleChangeBackgroundOverlay },
{ BP_PASSWORD_OK,       HandlePasswordOk },
{ BP_PASSWORD_NOT_OK,   HandlePasswordNotOk },
{ BP_ROUNDTRIP1,        HandleRoundtrip },
{ BP_CHANGE_TEXTURE,    HandleChangeTexture },
{ BP_SECTOR_LIGHT,      HandleSectorLight },
{ BP_SET_VIEW,          HandleSetView },
{ BP_RESET_VIEW,        HandleResetView },
{ 0, NULL},   // must end table this way
};

static BYTE ExtractPaletteTranslation(char** ptr, BYTE* translation, BYTE* effect);

static unsigned int server_secure_token = 0;
static char* server_sliding_token = NULL;
static char* _redbookstring = NULL;
static ID _redbook = 0;

void ResetSecurityToken()
{
    _redbook = 0;

    if (_redbookstring)
        free(_redbookstring);
    _redbookstring = NULL;

    server_secure_token = 0;
    server_sliding_token = NULL;
}

void UpdateSecurityRedbook(ID idRedbook)
{
    if (_redbookstring)
        free(_redbookstring);
    _redbookstring = NULL;

    _redbook = idRedbook;
    if (_redbook)
        _redbookstring = LookupRscRedbook(_redbook);

    if (_redbook && !_redbookstring)
    {
        debug(("UpdateSecurityRedbook: can't load resource %i for redbook\n", _redbook));
        _redbook = 0;
    }

    if (_redbookstring)
        _redbookstring = strdup(_redbookstring);
}

char* GetSecurityRedbook()
{
    if (!_redbookstring)
        return "BLAKSTON: Greenwich Q Zjiria";

    return _redbookstring;
}

/********************************************************************/
/*
 * Extract: Copy numbytes bytes from buf to result, and increment
 *    buf by numbytes.
 */
void Extract(char** buf, void* result, UINT numbytes)
{
    memcpy(result, *buf, numbytes);
    *buf += numbytes;
}
/********************************************************************/
/*
 * ExtractCoordinates:  Get a set of coordinates from ptr, and put
 *   it in the given variables.  Converts from 1-based server coordinates
 *   to 0-based client coordinates.  Also converts kod fineness to client fineness.
 */
void ExtractCoordinates(char** ptr, int* x, int* y)
{
    WORD word;

    Extract(ptr, &word, SIZE_COORD);
    *y = FinenessKodToClient(((int)word) - KOD_FINENESS);
    Extract(ptr, &word, SIZE_COORD);
    *x = FinenessKodToClient(((int)word) - KOD_FINENESS);
}
/********************************************************************/
/*
 * ExtractFlags:  Extract the object flag fields (obj flags, drawingflags,
 *   minimap, name color, object type, moveon type).
 */
void ExtractFlags(char** ptr, object_node* o)
{
    Extract(ptr, &o->flags, SIZE_VALUE);
    Extract(ptr, &o->drawingtype, SIZE_TYPE);
    Extract(ptr, &o->minimapflags, SIZE_VALUE);
    Extract(ptr, &o->namecolor, SIZE_VALUE);

    BYTE temptype = 0;
    Extract(ptr, &temptype, SIZE_TYPE);
    o->objecttype = (object_type)temptype;

    Extract(ptr, &temptype, SIZE_TYPE);
    o->moveontype = (moveon_type)temptype;
}
/********************************************************************/
/*
 * ExtractPaletteTranslation:  Get palette translation information from
 *   ptr, and increment ptr appropriately.  Return the translation
 *   type.
 */
BYTE ExtractPaletteTranslation(char** ptr, BYTE* translation, BYTE* effect)
{
    BYTE animation_type;
    char* oldptr = *ptr;

    *translation = 0;
    *effect = 0;

    // For special animation type, get palette translation info,
    // otherwise, back up 1 byte and read actual animation info.
    Extract(ptr, &animation_type, 1);
    if (animation_type == ANIMATE_TRANSLATION)
    {
        Extract(ptr, translation, 1);
    }
    else if (animation_type == ANIMATE_EFFECT)
    {
        Extract(ptr, effect, 1);
    }
    else
    {
        *ptr = oldptr;
    }

    return *translation | *effect;
}
/********************************************************************/
/*
 * ExtractAnimation: Get an animation structure from ptr, and increment
 *   ptr appropriately.  Place data in given animation structure.
 */
void ExtractAnimation(char** ptr, Animate* a)
{
    Extract(ptr, &a->animation, SIZE_ANIMATE);

    // Read animation-type dependent stuff
    switch (a->animation)
    {
    case ANIMATE_NONE:
        Extract(ptr, &a->group, SIZE_ANIMATE_GROUP);
        a->group = BitmapGroupSToC(a->group);
        break;

    case ANIMATE_CYCLE:
        Extract(ptr, &a->period, 4);
        Extract(ptr, &a->group_low, SIZE_ANIMATE_GROUP);
        Extract(ptr, &a->group_high, SIZE_ANIMATE_GROUP);
        a->group_low = BitmapGroupSToC(a->group_low);
        a->group_high = BitmapGroupSToC(a->group_high);
        a->group = a->group_low;
        a->tick = a->period;
        break;

    case ANIMATE_ONCE:
        Extract(ptr, &a->period, 4);
        Extract(ptr, &a->group_low, SIZE_ANIMATE_GROUP);
        Extract(ptr, &a->group_high, SIZE_ANIMATE_GROUP);
        Extract(ptr, &a->group_final, SIZE_ANIMATE_GROUP);
        a->group_low = BitmapGroupSToC(a->group_low);
        a->group_high = BitmapGroupSToC(a->group_high);
        a->group_final = BitmapGroupSToC(a->group_final);
        a->group = a->group_low;
        a->tick = a->period;
        break;

    default:
        debug(("Unknown animation type %d read from server\n", a->animation));
        a->group = 0;
        break;
    }
}
/********************************************************************/
/*
 * ExtractOverlays: Get overlay structures from ptr,
 *   and increment ptr appropriately.  Return list of overlays.
 */
list_type ExtractOverlays(char** ptr)
{
    int i;
    list_type l = NULL;
    BYTE num_overlays;

    Extract(ptr, &num_overlays, 1);

    if (num_overlays == 0)
        return NULL;

    for (i = 0; i < num_overlays; i++)
    {
        Overlay* overlay = (Overlay*)ZeroSafeMalloc(sizeof(Overlay));
        ExtractOverlay(ptr, overlay);
        l = list_add_item(l, overlay);
    }
    return l;
}
/********************************************************************/
/*
 * ExtractOverlay:  Fill overlay with data fom ptr,
 *   and increment ptr appropriately.
 */
void ExtractOverlay(char** ptr, Overlay* overlay)
{
    Extract(ptr, &overlay->icon_res, SIZE_ID);
    Extract(ptr, &overlay->hotspot, SIZE_HOTSPOT);

    ExtractPaletteTranslation(ptr, &overlay->translation, &overlay->effect);
    ExtractAnimation(ptr, &overlay->animate);
}

void ExtractDLighting(char** ptr, d_lighting* dLighting)
{
    Extract(ptr, &dLighting->flags, 2);

    if (LIGHT_FLAG_NONE == dLighting->flags)
    {
        dLighting->color = 0;
        dLighting->intensity = 0;
        return;
    }

    Extract(ptr, &dLighting->intensity, 1);
    Extract(ptr, &dLighting->color, 2);
}
/********************************************************************/
/*
 * ExtractObject: Get an object_node from ptr, and increment
 *   ptr appropriately.  Place data in given object node.
 */
void ExtractObject(char** ptr, object_node* item)
{
    Extract(ptr, &item->id, SIZE_ID);
    if (IsNumberObj(item->id))
        Extract(ptr, &item->amount, SIZE_AMOUNT);
    else
        item->amount = 0;
    Extract(ptr, &item->icon_res, SIZE_ID);
    Extract(ptr, &item->name_res, SIZE_ID);

    // Flag fields.
    ExtractFlags(ptr, item);

    ExtractDLighting(ptr, &item->dLighting);

    ExtractPaletteTranslation(ptr, &item->translation, &item->effect);
    item->normal_translation = item->translation;
    item->secondtranslation = XLAT_FILTERWHITE90;

    ExtractAnimation(ptr, &item->normal_animate);
    item->animate = &item->normal_animate;

    item->normal_overlays = ExtractOverlays(ptr);
    item->overlays = &item->normal_overlays;

    if (OF_BOUNCING == (OF_BOUNCING & item->flags))
    {
        item->bounceTime = (WORD)(rand() % 1000);
    }
    if (OF_PHASING == (OF_PHASING & item->flags))
    {
        item->phaseTime = (WORD)(rand() % 1000);
    }
}

void ExtractObjectNoLight(char** ptr, object_node* item)
{
    Extract(ptr, &item->id, SIZE_ID);
    if (IsNumberObj(item->id))
        Extract(ptr, &item->amount, SIZE_AMOUNT);
    else
        item->amount = 0;
    Extract(ptr, &item->icon_res, SIZE_ID);
    Extract(ptr, &item->name_res, SIZE_ID);

    ExtractFlags(ptr, item);

    ExtractPaletteTranslation(ptr, &item->translation, &item->effect);
    item->normal_translation = item->translation;
    item->secondtranslation = XLAT_FILTERWHITE90;

    ExtractAnimation(ptr, &item->normal_animate);
    item->animate = &item->normal_animate;

    item->normal_overlays = ExtractOverlays(ptr);
    item->overlays = &item->normal_overlays;

    if (OF_BOUNCING == (OF_BOUNCING & item->flags))
    {
        item->bounceTime = (WORD)(rand() % 1000);
    }
    if (OF_PHASING == (OF_PHASING & item->flags))
    {
        item->phaseTime = (WORD)(rand() % 1000);
    }
}

/********************************************************************/
/*
 * ExtractNewObject: Get an object_node from ptr, and increment
 *    ptr appropriately.  Return a newly allocated object containing
 *    read info.
 */
object_node* ExtractNewObject(char** ptr)
{
    object_node* item = ObjectGetBlank();
    ExtractObject(ptr, item);
    return item;
}

object_node* ExtractNewObjectNoLighting(char** ptr)
{
    object_node* item = ObjectGetBlank();
    ExtractObjectNoLight(ptr, item);
    return item;
}
/********************************************************************/
/*
 * ExtractNewRoomObject:  Get a room_contents_node from ptr, and increment
 *   ptr appropriately.  Return a newly allocated object containing
 *   read info.
 */
room_contents_node* ExtractNewRoomObject(char** ptr)
{
    WORD word;
    room_contents_node* r = (room_contents_node*)ZeroSafeMalloc(sizeof(room_contents_node));

    ExtractObject(ptr, &r->obj);

    //   ExtractDLighting(ptr, &r->obj.dLighting);

    ExtractCoordinates(ptr, &r->motion.x, &r->motion.y);
    r->moving = False;

    Extract(ptr, &word, SIZE_ANGLE);
    r->angle = ANGLE_STOC(word);

    ExtractPaletteTranslation(ptr, &r->motion.translation, &r->motion.effect);
    ExtractAnimation(ptr, &r->motion.animate);
    r->motion.overlays = ExtractOverlays(ptr);
    r->motion.move_animating = False;

    return r;
}
/********************************************************************/
/*
 * ExtractObjectList:  Get a list of objects from ptr, allocate space
 *   for the objects, and return the list.
 *   Len should be the remaining bytes at the beginning of the list,
 *   and the list should be the last component of the message.
 *   Return LIST_ERROR on error.
 */
list_type ExtractObjectList(char** ptr, long len)
{
    WORD list_len, i;
    char* start;
    list_type list = NULL;

    if (len < SIZE_LIST_LEN)
        return LIST_ERROR;
    len -= SIZE_LIST_LEN;

    Extract(ptr, &list_len, SIZE_LIST_LEN);

    start = *ptr;

    for (i = 0; i < list_len; i++)
        list = list_add_item(list, ExtractNewObject(ptr));
    len -= (*ptr - start);
    if (len != 0)
    {
        ObjectListDestroy(list);
        return LIST_ERROR;
    }
    return list;
}
/********************************************************************/
/*
 * ExtractNewBackgroundOverlay:  Allocate a new background overlay,
 *   read it from ptr, and return it.  Modifies ptr.
 */
BackgroundOverlay* ExtractNewBackgroundOverlay(char** ptr)
{
    WORD word;
    BackgroundOverlay* item = (BackgroundOverlay*)ZeroSafeMalloc(sizeof(BackgroundOverlay));

    Extract(ptr, &item->obj.id, SIZE_ID);
    Extract(ptr, &item->obj.icon_res, SIZE_ID);
    Extract(ptr, &item->obj.name_res, SIZE_ID);

    ExtractPaletteTranslation(ptr, &item->obj.translation, &item->obj.effect);
    ExtractAnimation(ptr, &item->obj.normal_animate);
    item->obj.animate = &item->obj.normal_animate;

    Extract(ptr, &word, 2);
    item->x = (int)word;
    Extract(ptr, &word, 2);
    item->y = (int)word;

    return item;
}
/********************************************************************/
/*
 * ExtractString:  Retrieve a string from ptr and place it in str.
 *   Extracts at most max_chars characters; returns -1 if length is bigger than this.
 *   Return new value of len (i.e. # of remaining bytes), or -1 on failure.
 */
WORD ExtractString(char** ptr, long len, char* message, int max_chars)
{
    WORD string_len;

    if (len < SIZE_STRING_LEN)
        return (WORD)-1;
    len -= SIZE_STRING_LEN;

    Extract(ptr, &string_len, SIZE_STRING_LEN);
    if (len < string_len || string_len > max_chars)
        return (WORD)-1;
    Extract(ptr, message, string_len);
    message[string_len] = '\0';
    len -= string_len;

    return (WORD)len;
}
/********************************************************************/
/*
 * DesecureByServerToken: The first byte of a packet is mangled.
 * The server_secure_token is the current mangling that the server is
 * using on the first byte of the packet.  The server can tell us a
 * new value to mangle/unmangle with, every now and then.
 */
Bool DesecureByServerToken(char* message, int len)
{
    if (!message || len <= 0)
        return False;

    *message = (*message) ^ (server_secure_token & 0xFF);

    //   debug(("Got msg type %u secured by %u\n", (unsigned char)message[0], (unsigned char)(server_secure_token & 0xFF)));

    if (server_sliding_token)
    {
        server_secure_token += ((*server_sliding_token) & 0x7F);
        server_sliding_token++;
        if (*server_sliding_token == '\0')
            server_sliding_token = GetSecurityRedbook();
    }

    return True;
}
/********************************************************************/
/*
 * HandleMessage: Handle messages arriving from the server.  len should
 *   be the length of message INCLUDING type byte;
 *   the first byte of the message should be the type (BP_CREATE, etc.).
 *   Return True iff message has correct format.
 */
Bool HandleMessage(char* message, int len)
{
    HandlerTable table;
    Bool handled;

    DesecureByServerToken(message, len);

    switch (state)
    {
    case STATE_CONNECTING:
        table = connecting_handler_table;
        break;

    case STATE_LOGIN:
        table = login_handler_table;
        break;

    case STATE_GAME:
        // See if a module wants to handle the message
        if (ModuleEvent(EVENT_SERVERMSG, message, len) == False)
            return True;

        table = game_handler_table;
        break;

    default:
        return False;
    }

    handled = LookupMessage(message, len, table);
    if (!handled)
        debug(("Got unknown message type %d from server\n", (int)(unsigned char)message[0]));
    return handled;
}
/********************************************************************/
/*
 * LookupMessage:  Dispatch the given message according to the given message
 *   handler table.
 *   Return True iff message successfully handled by one of the message handlers
 *   in the table.
 */
Bool LookupMessage(char* message, int len, HandlerTable table)
{
    char* ptr;
    unsigned char type;
    Bool success = False;
    int index;

    memcpy(&type, message, SIZE_TYPE);

    ptr = message + SIZE_TYPE;

    /* Look for message handler in table */
    index = 0;
    while (table[index].msg_type != 0)
    {
        if (table[index].msg_type == type)
        {
            if (table[index].handler != NULL)
            {
                /* Don't count type byte in length for handler */
                success = (*table[index].handler)(ptr, len - SIZE_TYPE);
                if (!success)
                {
                    // Don't print error message for "subprotocols"; these handle themselves
                    if (type != BP_USERCOMMAND)
                        debug(("Error in message of type %d from server\n", type));
                    return False;
                }
            }
            break;
        }
        index++;
    }

    if (table[index].msg_type == 0)
        return False;
    return True;
}
/********************************************************************/
/*                      GAME MODE MESSAGES                          */
/********************************************************************/
Bool HandlePlayer(char* ptr, long len)
{
    player_info player;
    ID bkgnd_id;
    BYTE ambient_light;
    DWORD flags, depth;
    char* start = ptr;

    Extract(&ptr, &player.id, SIZE_ID);
    Extract(&ptr, &player.icon_res, SIZE_ID);
    Extract(&ptr, &player.name_res, SIZE_ID);
    Extract(&ptr, &player.room_id, SIZE_ID);
    Extract(&ptr, &player.room_res, SIZE_ID);
    Extract(&ptr, &player.room_name_res, SIZE_ID);
    Extract(&ptr, &player.room_security, 4);

    Extract(&ptr, &ambient_light, SIZE_LIGHT);
    Extract(&ptr, &player.light, SIZE_LIGHT);

    Extract(&ptr, &bkgnd_id, SIZE_ID);

    Extract(&ptr, &effects.wadingsound, SIZE_ID);

    Extract(&ptr, &flags, SIZE_VALUE);
    SetRoomFlags(flags);

    Extract(&ptr, &depth, SIZE_VALUE);
    SetOverrideRoomDepth(SF_DEPTH1, depth << 4);

    Extract(&ptr, &depth, SIZE_VALUE);
    SetOverrideRoomDepth(SF_DEPTH2, depth << 4);

    Extract(&ptr, &depth, SIZE_VALUE);
    SetOverrideRoomDepth(SF_DEPTH3, depth << 4);

    len -= (ptr - start);
    if (len != 0)
        return False;

    SetPlayerInfo(&player, ambient_light, bkgnd_id);
    return True;
}
/********************************************************************/
Bool HandleRoomContents(char* ptr, long len)
{
    room_contents_node* room_item;
    list_type room_contents_list = NULL;
    WORD list_len;
    int i;
    ID room_id;
    char* start;

    if (len < SIZE_ID + SIZE_LIST_LEN)
        return False;
    len -= SIZE_ID + SIZE_LIST_LEN;

    Extract(&ptr, &room_id, SIZE_ID);

    //   Extract(&ptr, &effects.wadingsound, SIZE_ID);
    //   Extract(&ptr, &current_room.flags, SIZE_VALUE);

    Extract(&ptr, &list_len, SIZE_LIST_LEN);

    start = ptr;
    for (i = 0; i < list_len; i++)
    {
        room_item = ExtractNewRoomObject(&ptr);
        room_contents_list = list_add_item(room_contents_list, room_item);
    }
    len -= (ptr - start);

    if (len != 0)
    {
        RoomObjectListDestroy(room_contents_list);
        return False;
    }

    SetPlayerRemoteView(0, 0, 0, 0);
    SetRoomInfo(room_id, room_contents_list);
    return True;
}
/********************************************************************/
Bool HandleRoomContentsFlags(char* ptr, long len)
{
    //StartWatch();
    WORD list_len;
    int i;
    ID room_id;
    char* start;
    ID object_id;
    room_contents_node* r;

    if (len < SIZE_ID + SIZE_LIST_LEN)
        return False;
    len -= SIZE_ID + SIZE_LIST_LEN;

    Extract(&ptr, &room_id, SIZE_ID);

    Extract(&ptr, &list_len, SIZE_LIST_LEN);
    start = ptr;
    bool found = false;
    for (i = 0; i < list_len; i++)
    {
        Extract(&ptr, &object_id, SIZE_ID);
        r = GetRoomObjectById(object_id);
        if (!r)
        {
            ptr += SIZE_OBJECTFLAGS;
            continue;
        }
        ExtractFlags(&ptr, &r->obj);

        found = true;
    }

    if (found)
        RedrawAll();

    len -= (ptr - start);

    //char buffer[BORDER_DEBUG_LENGTH];
    //sprintf(buffer, "Handled in %.3f us", StopWatch());
    //DrawDebugDataInBorder(buffer);

    return True;
}
/********************************************************************/
Bool HandleMove(char* ptr, long len)
{
    ID obj_id;
    int x, y;
    BYTE speed;
    WORD angle;
    char* start = ptr;
    BOOL turnToFace = FALSE;

    if (len < 1 * SIZE_ID + 2 * SIZE_COORD + 1 + SIZE_ANGLE)
        return False;

    Extract(&ptr, &obj_id, sizeof(obj_id));
    ExtractCoordinates(&ptr, &x, &y);

    Extract(&ptr, &speed, 1);
    if (0x80 & speed)
    {
        speed &= ~0x80;
        turnToFace = TRUE;
    }

    Extract(&ptr, &angle, sizeof(angle));

    len -= (ptr - start);
    if (len != 0)
        return False;

    TurnObject(obj_id, angle);
    MoveObject2(obj_id, x, y, speed, turnToFace);

    return True;
}
/********************************************************************/
Bool HandleTurn(char* ptr, long len)
{
    ID obj_id;
    WORD angle;

    if (len != SIZE_ID + SIZE_ANGLE)
        return False;

    Extract(&ptr, &obj_id, sizeof(obj_id));
    Extract(&ptr, &angle, sizeof(angle));
    TurnObject(obj_id, angle);

    return True;
}
/********************************************************************/
Bool HandleCreate(char* ptr, long len)
{
    room_contents_node* room_item;
    char* start = ptr;

    room_item = ExtractNewRoomObject(&ptr);

    len -= (ptr - start);
    if (len != 0)
    {
        SafeFree(room_item);
        return False;
    }

    CreateObject(room_item);

    return True;
}
/********************************************************************/
Bool HandleRemove(char* ptr, long len)
{
    ID obj_id;

    if (len != 1 * SIZE_ID)
        return False;

    Extract(&ptr, &obj_id, SIZE_ID);

    RemoveObject(obj_id);

    return True;
}
/********************************************************************/
Bool HandleChange(char* ptr, long len)
{
    object_node object;
    Animate a;
    list_type overlays;
    BYTE translation = 255;
    BYTE effect = 255;
    char* start = ptr;

    memset(&object, 0, sizeof(object));
    ExtractObject(&ptr, &object);
    //   ExtractDLighting(&ptr, &object.dLighting);
    ExtractPaletteTranslation(&ptr, &translation, &effect);
    ExtractAnimation(&ptr, &a);
    overlays = ExtractOverlays(&ptr);

    len -= (ptr - start);
    if (len != 0)
        return False;

    ChangeObject(&object, translation, effect, &a, overlays);

    return True;
}
/********************************************************************/
Bool HandleChangeFlags(char* ptr, long len)
{
    char* start;
    object_node o;

    if (len < SIZE_ID + SIZE_OBJECTFLAGS)
        return False;

    start = ptr;

    Extract(&ptr, &o.id, SIZE_ID);
    ExtractFlags(&ptr, &o);

    len -= (ptr - start);
    if (len != 0)
        return False;

    ChangeObjectFlags(&o);

    return True;
}
/********************************************************************/
Bool HandleObjectContents(char* ptr, long len)
{
    list_type list = NULL;
    ID object_id;

    if (len < SIZE_ID)
        return False;

    Extract(&ptr, &object_id, SIZE_ID);
    len -= SIZE_ID;

    if ((list = ExtractObjectList(&ptr, len)) == LIST_ERROR)
        return False;

    GotObjectContents(object_id, list);
    return True;
}
/********************************************************************/
Bool HandleInventoryAdd(char* ptr, long len)
{
    object_node* obj;
    char* start = ptr;

    obj = ExtractNewObject(&ptr);
    len -= (ptr - start);
    if (len != 0)
    {
        SafeFree(obj);
        return False;
    }

    AddToInventory(obj);
    return True;
}
/********************************************************************/
Bool HandleInventoryRemove(char* ptr, long len)
{
    ID obj_id;

    if (len != SIZE_ID)
        return False;

    Extract(&ptr, &obj_id, SIZE_ID);

    RemoveFromInventory(obj_id);

    return True;
}
/********************************************************************/
Bool HandleInventory(char* ptr, long len)
{
    list_type list = NULL;

    if ((list = ExtractObjectList(&ptr, len)) == LIST_ERROR)
        return False;

    SetInventory(list);
    return True;
}
/********************************************************************/
Bool HandleStringMessage(char* ptr, long len)
{
    char message[MAXMESSAGE];
    char* msg = message;
    ID resource_id;

    if (len < SIZE_ID)
        return False;

    Extract(&ptr, &resource_id, SIZE_ID);
    len -= SIZE_ID;

    // See if we need to reorder the message.
    if (CheckMessageOrder(&ptr, &len, resource_id) < 0)
        return False;
    /* Remove format string id # from length */
    if (!CheckServerMessage(&msg, &ptr, &len, resource_id))
        return False;

    GameMessage(msg);
    return True;
}
/********************************************************************/
Bool HandleSysMessage(char* ptr, long len)
{
    // System messages used to be handled and displayed separately; now
    // we just display them in the main text area.
    return HandleStringMessage(ptr, len);
}
/********************************************************************/
Bool HandleSaid(char* ptr, long len)
{
    char message[MAXMESSAGE];
    char* msg = message;
    ID resource_id, sender_id, sender_name;
    BYTE say_type;

    if (len < SIZE_ID)
        return False;

    Extract(&ptr, &sender_id, SIZE_ID);
    Extract(&ptr, &sender_name, SIZE_ID);
    Extract(&ptr, &say_type, SIZE_SAY_INFO);
    Extract(&ptr, &resource_id, SIZE_ID);

    len -= 2 * SIZE_ID + SIZE_SAY_INFO;

    if (!CheckServerMessage(&msg, &ptr, &len, resource_id))
        return False;

    MessageSaid(sender_id, sender_name, say_type, msg);
    return True;
}
/********************************************************************/
Bool HandleInvalidateData(char* ptr, long len)
{
    if (len != 0)
        return False;
    ResetUserData();
    return True;
}
/********************************************************************/
Bool HandleWait(char* ptr, long len)
{
    if (len != 0)
        return False;

    //   System is saving - clear user selected target as the ID will be invalid afterwards.
    SetUserTargetID(INVALID_ID);

    GameWait();
    return True;
}
/********************************************************************/
Bool HandleUnwait(char* ptr, long len)
{
    if (len != 0)
        return False;

    GameUnwait();
    return True;
}
/********************************************************************/
Bool HandleLook(char* ptr, long len)
{
    char message[MAXMESSAGE];
    char* msg = message;
    char inscription[MAXMESSAGE];
    char* inscr = inscription;
    ID resource_id;
    BYTE flags;
    BOOL pane;
    char* start = ptr;
    object_node obj;

    memset(&obj, 0, sizeof(obj));
    ExtractObject(&ptr, &obj);
    Extract(&ptr, &flags, 1);

    // Remove format string id # & other ids from length
    Extract(&ptr, &resource_id, SIZE_ID);
    len -= (ptr - start);
    // See if we need to reorder the message.
    if (CheckMessageOrder(&ptr, &len, resource_id) < 0)
        return False;
    if (!CheckServerMessage(&msg, &ptr, &len, resource_id))
        return False;

    // Get inscription string
    inscription[0] = '\0';
    pane = TRUE && flags & (DF_EDITABLE | DF_INSCRIBED);
    if (pane)
    {
        Extract(&ptr, &resource_id, SIZE_ID);
        len -= SIZE_ID;
        if (!CheckServerMessage(&inscr, &ptr, &len, resource_id))
            return False;
    }

    DisplayDescription(&obj, flags, (pane ? inscr : NULL), msg, NULL, NULL, 0, 0, 0);
    ObjectDestroy(&obj);

    return True;
}
/********************************************************************/
Bool HandleLookSpell(char* ptr, long len)
{
    char message[MAXMESSAGE];
    char* msg = message;
    char school_name[MAXMESSAGE];
    char* sname = school_name;
    char spell_level[MAXMESSAGE];
    char* slevel = spell_level;
    char spell_mana[MAXMESSAGE];
    char* smana = spell_mana;
    char spell_vigor[MAXMESSAGE];
    char* svigor = spell_vigor;

    ID resource_id;
    char* start = ptr;
    object_node obj;

    memset(&obj, 0, sizeof(obj));
    ExtractObject(&ptr, &obj);

    len -= (ptr - start);

    // School name.
    Extract(&ptr, &resource_id, SIZE_ID);
    len -= SIZE_ID;
    if (!CheckServerMessage(&sname, &ptr, &len, resource_id))
        return False;
    // Spell level.
    Extract(&ptr, &resource_id, SIZE_ID);
    len -= SIZE_ID;
    if (!CheckServerMessage(&slevel, &ptr, &len, resource_id))
        return False;
    // Spell mana cost.
    Extract(&ptr, &resource_id, SIZE_ID);
    len -= SIZE_ID;
    if (!CheckServerMessage(&smana, &ptr, &len, resource_id))
        return False;
    // Spell vigor cost.
    Extract(&ptr, &resource_id, SIZE_ID);
    len -= SIZE_ID;
    if (!CheckServerMessage(&svigor, &ptr, &len, resource_id))
        return False;

    // Description.
    Extract(&ptr, &resource_id, SIZE_ID);
    len -= SIZE_ID;
    // See if we need to reorder the message.
    if (CheckMessageOrder(&ptr, &len, resource_id) < 0)
        return False;
    if (!CheckServerMessage(&msg, &ptr, &len, resource_id))
        return False;

    DisplayDescription(&obj, 0, NULL, msg, NULL, sname, slevel, smana, svigor);
    ObjectDestroy(&obj);

    return True;
}
/********************************************************************/
Bool HandleLookSkill(char* ptr, long len)
{
    char message[MAXMESSAGE];
    char* msg = message;
    char school_name[MAXMESSAGE];
    char* sname = school_name;
    char skill_level[MAXMESSAGE];
    char* slevel = skill_level;

    ID resource_id;
    char* start = ptr;
    object_node obj;

    memset(&obj, 0, sizeof(obj));
    ExtractObject(&ptr, &obj);

    len -= (ptr - start);

    // School name.
    Extract(&ptr, &resource_id, SIZE_ID);
    len -= SIZE_ID;
    if (!CheckServerMessage(&sname, &ptr, &len, resource_id))
        return False;
    // Skill level.
    Extract(&ptr, &resource_id, SIZE_ID);
    len -= SIZE_ID;
    if (!CheckServerMessage(&slevel, &ptr, &len, resource_id))
        return False;

    // Description.
    Extract(&ptr, &resource_id, SIZE_ID);
    len -= SIZE_ID;
    // See if we need to reorder the message.
    if (CheckMessageOrder(&ptr, &len, resource_id) < 0)
        return False;
    if (!CheckServerMessage(&msg, &ptr, &len, resource_id))
        return False;

    DisplayDescription(&obj, 0, NULL, msg, NULL, sname, slevel, NULL, NULL);
    ObjectDestroy(&obj);

    return True;
}
/********************************************************************/
Bool HandleUseList(char* ptr, long len)
{
    list_type use_list = NULL;
    WORD list_len;
    int i;
    ID id;
    char* start;

    if (len < SIZE_LIST_LEN)
        return False;
    len -= SIZE_LIST_LEN;

    Extract(&ptr, &list_len, SIZE_LIST_LEN);

    start = ptr;

    for (i = 0; i < list_len; i++)
    {
        Extract(&ptr, &id, SIZE_ID);
        use_list = list_add_item(use_list, (void*)id);
    }

    len -= (ptr - start);
    if (len != 0)
    {
        list_delete(use_list);
        return False;
    }

    UseListSet(use_list);
    return True;
}
/********************************************************************/
Bool HandleUse(char* ptr, long len)
{
    ID obj_id;

    if (len != SIZE_ID)
        return False;

    Extract(&ptr, &obj_id, SIZE_ID);

    UseObject(obj_id);
    return True;
}
/********************************************************************/
Bool HandleUnuse(char* ptr, long len)
{
    ID obj_id;

    if (len != SIZE_ID)
        return False;

    Extract(&ptr, &obj_id, SIZE_ID);

    UnuseObject(obj_id);
    return True;
}
/********************************************************************/
Bool HandleOffer(char* ptr, long len)
{
    list_type list = NULL;
    object_node offerer;
    char* start;

    start = ptr;

    memset(&offerer, 0, sizeof(offerer));
    /* Object that offered to player */
    ExtractObject(&ptr, &offerer);
    len -= (ptr - start);

    if ((list = ExtractObjectList(&ptr, len)) == LIST_ERROR)
        return False;

    ReceiveOffer(offerer.id, offerer.icon_res, offerer.name_res, list);
    return True;
}
/********************************************************************/
Bool HandleOfferCanceled(char* ptr, long len)
{
    if (len != 0)
        return False;

    OfferCanceled();
    return True;
}
/********************************************************************/
Bool HandleOffered(char* ptr, long len)
{
    list_type list = NULL;

    if ((list = ExtractObjectList(&ptr, len)) == LIST_ERROR)
        return False;

    Offered(list);
    return True;
}
/********************************************************************/
Bool HandleCounteroffered(char* ptr, long len)
{
    list_type list = NULL;

    if ((list = ExtractObjectList(&ptr, len)) == LIST_ERROR)
        return False;

    Counteroffered(list);
    return True;
}
/********************************************************************/
Bool HandleCounteroffer(char* ptr, long len)
{
    list_type list = NULL;

    if ((list = ExtractObjectList(&ptr, len)) == LIST_ERROR)
        return False;

    Counteroffer(list);
    return True;
}
/********************************************************************/
Bool HandlePlayers(char* ptr, long len)
{
    list_type list = NULL;
    WORD list_len;
    int i;
    char name[MAXNAME + 1];
    char* start = ptr;
    object_node* obj;

    Extract(&ptr, &list_len, SIZE_LIST_LEN);
    len -= SIZE_LIST_LEN;

    for (i = 0; i < list_len; i++)
    {
        obj = ObjectGetBlank();

        Extract(&ptr, &obj->id, SIZE_ID);
        Extract(&ptr, &obj->name_res, SIZE_ID);
        len -= 2 * SIZE_ID;

        // Get username and add it as a resource
        len = ExtractString(&ptr, len, name, MAXNAME);
        ChangeResource(obj->name_res, name);

        // Flags
        ExtractFlags(&ptr, obj);
        len -= SIZE_OBJECTFLAGS;

        list = list_add_item(list, obj);
    }

    if (len != 0)
    {
        ObjectListDestroy(list);
        return False;
    }

    SetCurrentUsers(list);
    return True;
}
/********************************************************************/
Bool HandleAddPlayer(char* ptr, long len)
{
    object_node* obj;
    char* start = ptr;
    char name[MAXNAME + 1];

    obj = ObjectGetBlank();
    Extract(&ptr, &obj->id, SIZE_ID);
    Extract(&ptr, &obj->name_res, SIZE_ID);
    len -= 2 * SIZE_ID;

    len = ExtractString(&ptr, len, name, MAXNAME);
    ChangeResource(obj->name_res, name);

    // Flags
    ExtractFlags(&ptr, obj);
    len -= SIZE_OBJECTFLAGS;

    if (len != 0)
    {
        ObjectDestroyAndFree(obj);
        return False;
    }

    AddCurrentUser(obj);
    return True;
}
/********************************************************************/
Bool HandleBuyList(char* ptr, long len)
{
    object_node seller;
    buy_object* buy_obj;
    list_type list = NULL;
    WORD list_len;
    char* start;
    int i;

    start = ptr;
    memset(&seller, 0, sizeof(seller));
    /* Get seller */
    ExtractObject(&ptr, &seller);
    //   ExtractDLighting(&ptr, &seller.dLighting);
    Extract(&ptr, &list_len, SIZE_LIST_LEN);

    for (i = 0; i < list_len; i++)
    {
        buy_obj = (buy_object*)ZeroSafeMalloc(sizeof(buy_object));
        ExtractObject(&ptr, &buy_obj->obj);
        //     ExtractDLighting(&ptr, &buy_obj->obj.dLighting);
        Extract(&ptr, &buy_obj->cost, SIZE_COST);

        list = list_add_item(list, buy_obj);
    }

    len -= (ptr - start);
    //   if (len != 0)
    if (0)
    {
        ObjectListDestroy(list);
        return False;
    }
    BuyList(seller, list);

    return True;
}
/********************************************************************/
Bool HandleWithdrawalList(char* ptr, long len)
{
    object_node seller;
    buy_object* buy_obj;
    list_type list = NULL;
    WORD list_len;
    char* start;
    int i;

    start = ptr;
    memset(&seller, 0, sizeof(seller));
    /* Get seller */
    ExtractObject(&ptr, &seller);
    Extract(&ptr, &list_len, SIZE_LIST_LEN);

    for (i = 0; i < list_len; i++)
    {
        buy_obj = (buy_object*)ZeroSafeMalloc(sizeof(buy_object));
        ExtractObject(&ptr, &buy_obj->obj);
        Extract(&ptr, &buy_obj->cost, SIZE_COST);

        list = list_add_item(list, buy_obj);
    }

    len -= (ptr - start);
    if (len != 0)
    {
        ObjectListDestroy(list);
        return False;
    }
    WithdrawalList(seller, list);

    return True;
}
/********************************************************************/
Bool HandleRemovePlayer(char* ptr, long len)
{
    ID obj_id;

    if (len != SIZE_ID)
        return False;

    Extract(&ptr, &obj_id, SIZE_ID);

    RemoveCurrentUser(obj_id);
    return True;
}
/********************************************************************/
Bool HandlePlayWave(char* ptr, long len)
{
    ID rsc, obj;
    BYTE flags;
    int row, col;
    int radius, maxvol;

    if (len != 6 * SIZE_ID + 1)
        return False;

    Extract(&ptr, &rsc, SIZE_ID);
    Extract(&ptr, &obj, SIZE_ID);
    Extract(&ptr, &flags, 1);
    Extract(&ptr, &row, sizeof(row));
    Extract(&ptr, &col, sizeof(col));
    Extract(&ptr, &radius, sizeof(radius));
    Extract(&ptr, &maxvol, sizeof(maxvol));

    // client overrides any volume setting the server might think it should be
    maxvol = config.sound_volume;

    GamePlaySound(rsc, obj, flags, row, col, radius, maxvol);
    return True;
}
/********************************************************************/
Bool HandleStopWave(char* ptr, long len)
{
    ID rsc, obj;

    if (len != 2 * SIZE_ID)
        return False;

    Extract(&ptr, &rsc, SIZE_ID);
    Extract(&ptr, &obj, SIZE_ID);

    SoundStopResource(rsc, obj);
    return True;
}
/********************************************************************/
Bool HandlePlayMidi(char* ptr, long len)
{
    ID rsc;

    if (len != SIZE_ID)
        return False;

    Extract(&ptr, &rsc, SIZE_ID);

    MusicPlayResource(rsc);
    return True;
}
/********************************************************************/
Bool HandlePlayMusic(char* ptr, long len)
{
    ID rsc;

    if (len != SIZE_ID)
        return False;

    Extract(&ptr, &rsc, SIZE_ID);

    MusicPlayResource(rsc);
    return True;
}
/********************************************************************/
Bool HandleQuit(char* ptr, long len)
{
    if (len != 0)
        return False;
    GameQuit();
    return True;
}
/********************************************************************/
Bool HandleLightAmbient(char* ptr, long len)
{
    BYTE light;

    if (len != SIZE_LIGHT)
        return False;

    Extract(&ptr, &light, SIZE_LIGHT);
    SetAmbientLight(light);
    gD3DRedrawAll |= D3DRENDER_REDRAW_UPDATE;

    return True;
}
/********************************************************************/
Bool HandleLightPlayer(char* ptr, long len)
{
    BYTE light;

    if (len != SIZE_LIGHT)
        return False;

    Extract(&ptr, &light, SIZE_LIGHT);
    SetPlayerLight(light);
    gD3DRedrawAll |= D3DRENDER_REDRAW_UPDATE;

    return True;
}
/********************************************************************/
Bool HandleBackground(char* ptr, long len)
{
    ID bkgnd;

    if (len != SIZE_ID)
        return False;

    Extract(&ptr, &bkgnd, SIZE_ID);
    SetBackground(bkgnd);
    return True;
}
/********************************************************************/
Bool HandleEffect(char* ptr, long len)
{
    WORD effect_num;

    Extract(&ptr, &effect_num, 2);
    len -= 2;
    return PerformEffect(effect_num, ptr, len);
}
/********************************************************************/
Bool HandleMovementSpeed(char* ptr, long len)
{
    WORD movespeedpct;

    Extract(&ptr, &movespeedpct, 2);
    len -= 2;
    return True;
}
/********************************************************************/
Bool HandleShoot(char* ptr, long len)
{
    Projectile* p = (Projectile*)ZeroSafeMalloc(sizeof(Projectile));
    BYTE speed;
    char* start = ptr;
    ID source, dest;
    WORD flags;
    WORD reserved;

    Extract(&ptr, &p->icon_res, SIZE_ID);
    ExtractPaletteTranslation(&ptr, &p->translation, &p->effect);
    ExtractAnimation(&ptr, &p->animate);

    Extract(&ptr, &source, SIZE_ID);
    Extract(&ptr, &dest, SIZE_ID);
    Extract(&ptr, &speed, 1);
    Extract(&ptr, &flags, SIZE_PROJECTILE_FLAGS);

    // no longer sent by the server
    //Extract(&ptr, &reserved, SIZE_PROJECTILE_RESERVED);
    reserved = 0;
    ExtractDLighting(&ptr, &p->dLighting);

    len -= (ptr - start);
    if (len != 0)
        return False;

    ProjectileAdd(p, source, dest, speed, flags, reserved);

    return True;
}
/********************************************************************/
Bool HandleRadiusShoot(char* ptr, long len)
{
    Projectile* p = (Projectile*)ZeroSafeMalloc(sizeof(Projectile));
    BYTE speed, range;
    char* start = ptr;
    ID source;
    WORD flags;
    WORD reserved;
    BYTE number;

    Extract(&ptr, &p->icon_res, SIZE_ID);
    ExtractPaletteTranslation(&ptr, &p->translation, &p->effect);
    ExtractAnimation(&ptr, &p->animate);

    Extract(&ptr, &source, SIZE_ID);
    Extract(&ptr, &speed, 1);
    Extract(&ptr, &flags, SIZE_PROJECTILE_FLAGS);

    // no longer sent by the server
    //Extract(&ptr, &reserved, SIZE_PROJECTILE_RESERVED);
    reserved = 0;
    Extract(&ptr, &range, 1);
    Extract(&ptr, &number, 1);
    ExtractDLighting(&ptr, &p->dLighting);

    len -= (ptr - start);
    if (len != 0)
        return False;

    RadiusProjectileAdd(p, source, speed, flags, reserved, range, number);

    return True;
}
/********************************************************************/
Bool HandleLoadModule(char* ptr, long len)
{
    ID name_rsc;

    if (len != SIZE_ID)
        return False;

    Extract(&ptr, &name_rsc, SIZE_ID);

    ModuleLoadByRsc(name_rsc);

    return True;
}
/********************************************************************/
Bool HandleUnloadModule(char* ptr, long len)
{
    ID name_rsc;

    if (len != SIZE_ID)
        return False;

    Extract(&ptr, &name_rsc, SIZE_ID);

    ModuleExitByRsc(name_rsc);

    return True;
}
/********************************************************************/
Bool HandleChangeResource(char* ptr, long len)
{
    char res_string[MAXNAME + 1];
    ID res;

    if (len < SIZE_ID)
        return False;

    Extract(&ptr, &res, SIZE_ID);
    len -= SIZE_ID;

    len = ExtractString(&ptr, len, res_string, MAXNAME);
    if (len != 0)
        return False;

    ChangeResource(res, res_string);

    return True;
}
/********************************************************************/
Bool HandlePlayerOverlay(char* ptr, long len)
{
    object_node* poverlay;
    char* start = ptr;
    char hotspot;

    Extract(&ptr, &hotspot, SIZE_HOTSPOT);

    poverlay = ExtractNewObjectNoLighting(&ptr);

    len -= (ptr - start);
    if (len != 0)
    {
        ObjectDestroyAndFree(poverlay);
        return False;
    }

    SetPlayerOverlay(hotspot, poverlay);
    return True;
}
/********************************************************************/
Bool HandleSectorMove(char* ptr, long len)
{
    WORD sector_num, height;
    BYTE speed, type;

    Extract(&ptr, &type, 1);
    Extract(&ptr, &sector_num, 2);
    Extract(&ptr, &height, 2);
    Extract(&ptr, &speed, 1);

    MoveSector(type, sector_num, height, speed);

    return True;
}
/********************************************************************/
Bool HandleWallAnimate(char* ptr, long len)
{
    WORD wall_num;
    Animate a;
    BYTE action;

    Extract(&ptr, &wall_num, 2);
    ExtractAnimation(&ptr, &a);
    Extract(&ptr, &action, 1);

    WallChange(wall_num, &a, action);
    return True;
}
/********************************************************************/
Bool HandleSectorAnimate(char* ptr, long len)
{
    WORD sector_num;
    Animate a;
    BYTE action;

    Extract(&ptr, &sector_num, 2);
    ExtractAnimation(&ptr, &a);
    Extract(&ptr, &action, 1);

    SectorAnimate(sector_num, &a, action);
    return True;
}
/********************************************************************/
Bool HandleSectorChange(char* ptr, long len)
{
    WORD sector_num;
    BYTE depth, scroll;

    Extract(&ptr, &sector_num, 2);
    Extract(&ptr, &depth, 1);
    Extract(&ptr, &scroll, 1);

    SectorChange(sector_num, depth, scroll);
    return True;
}
/********************************************************************/
Bool HandleAddBackgroundOverlay(char* ptr, long len)
{
    BackgroundOverlay* overlay;
    char* start = ptr;

    overlay = ExtractNewBackgroundOverlay(&ptr);

    if (ptr - start != len)
    {
        BackgroundOverlayDestroyAndFree(overlay);
        return False;
    }

    BackgroundOverlayAdd(overlay);
    return True;
}
/********************************************************************/
Bool HandleRemoveBackgroundOverlay(char* ptr, long len)
{
    ID id;

    if (len != SIZE_ID)
        return False;

    Extract(&ptr, &id, SIZE_ID);

    BackgroundOverlayRemove(id);

    return True;
}
/********************************************************************/
Bool HandleChangeBackgroundOverlay(char* ptr, long len)
{
    BackgroundOverlay* overlay;
    char* start = ptr;

    overlay = ExtractNewBackgroundOverlay(&ptr);

    if (ptr - start != len)
    {
        BackgroundOverlayDestroyAndFree(overlay);
        return False;
    }

    BackgroundOverlayChange(overlay);
    return True;
}
/********************************************************************/
Bool HandleRoundtrip(char* ptr, long len)
{
    DWORD data;

    if (len != 4)
        return False;

    Extract(&ptr, &data, 4);
    RequestRoundtrip(data);

    return True;
}
/********************************************************************/
Bool HandleChangeTexture(char* ptr, long len)
{
    WORD id_num, texture_num;
    BYTE flags;

    char* start = ptr;

    Extract(&ptr, &id_num, 2);
    Extract(&ptr, &texture_num, 2);
    Extract(&ptr, &flags, 1);

    if (ptr - start != len)
        return False;

    TextureChange(id_num, texture_num, flags);
    gD3DRedrawAll |= D3DRENDER_REDRAW_ALL;
    return True;
}
/********************************************************************/
Bool HandleSectorLight(char* ptr, long len)
{
    WORD sector_num;
    BYTE type;

    char* start = ptr;

    Extract(&ptr, &sector_num, 2);
    Extract(&ptr, &type, 1);

    if (ptr - start != len)
        return False;

    SectorFlickerChange(sector_num, type);
    return True;
}
/********************************************************************/
Bool HandleLightShading(char* ptr, long len)
{
    WORD sun_x, sun_y;
    BYTE directional_light;
    char* start = ptr;

    Extract(&ptr, &directional_light, SIZE_LIGHT);
    Extract(&ptr, &sun_x, 2);
    Extract(&ptr, &sun_y, 2);

    SetLightingInfo(sun_x, sun_y, directional_light);
    gD3DRedrawAll |= D3DRENDER_REDRAW_UPDATE;

    return True;
}
/********************************************************************/
Bool HandleEchoPing(char* ptr, long len)
{
    if (len > 0 && ptr != NULL)
    {
        char ch;
        int id;

        Extract(&ptr, &ch, 1);
        Extract(&ptr, &id, 4);
        len -= 5;

        server_secure_token = (unsigned int)(ch ^ 0xED);

        UpdateSecurityRedbook(id);

        server_sliding_token = GetSecurityRedbook();

        // debug(("New redbook is '%s'.\n", server_sliding_token));
    }

    if (len != 0)
        return False;
    PingGotReply();
    return True;
}
/********************************************************************/
Bool HandleEchoUDPPing(char* ptr, long len)
{
    if (len != 0)
        return False;
    PingGotReplyUDP();
    return True;
}
/********************************************************************/
/*                      LOGIN MODE MESSAGES                         */
/********************************************************************/
Bool HandleLoginOk(char* ptr, long len)
{
    BYTE admin;
    int sessionid;

    if (len != (SIZE_ADMIN + SIZE_SESSION_ID))
        return False;

    Extract(&ptr, &admin, SIZE_ADMIN);
    Extract(&ptr, &sessionid, SIZE_SESSION_ID);
    LoginOk(admin, sessionid);
    return True;
}
/********************************************************************/
Bool HandleLoginFailed(char* ptr, long len)
{
    if (len != 0)
        return False;
    LoginError(IDS_BADLOGIN);
    return True;
}
/********************************************************************/
Bool HandleEnterGame(char* ptr, long len)
{
    if (len != 0)
        return False;
    MainSetState(STATE_GAME);
    return True;
}
/********************************************************************/
Bool HandleEnterAdmin(char* ptr, long len)
{
    if (len != 0)
        return False;
    MainSetState(STATE_TERM);
    return True;
}
/********************************************************************/
Bool HandleGetLogin(char* ptr, long len)
{
    if (len != 0)
        return False;
    LoginSendInfo();
    return True;
}
/********************************************************************/
Bool HandleGetChoice(char* ptr, long len)
{
    int i;
    unsigned int seeds[NUM_STREAMS];

    if (len != NUM_STREAMS * 4)
        return False;

    for (i = 0; i < NUM_STREAMS; i++)
        Extract(&ptr, &seeds[i], 4);

    RandomStreamsInit(seeds);
    EnterGame();
    return True;
}
/********************************************************************/
Bool HandleLoginErrorMsg(char* ptr, long len)
{
    char message[MAXMESSAGE + 1];
    BYTE action;

    len = ExtractString(&ptr, len, message, MAXMESSAGE);
    if (len != 1)
        return False;
    Extract(&ptr, &action, 1);
    LoginErrorMessage(message, action);
    return True;
}
/********************************************************************/
Bool HandleAccountUsed(char* ptr, long len)
{
    if (len != 0)
        return False;
    LoginError(IDS_ACCOUNTUSED);
    return True;
}
/********************************************************************/
Bool HandleTooManyLogins(char* ptr, long len)
{
    if (len != 0)
        return False;
    LoginError(IDS_TOOMANYLOGINS);
    return True;
}
/********************************************************************/
Bool HandleTimeout(char* ptr, long len)
{
    if (len != 0)
        return False;
    LoginTimeout();
    return True;
}
/********************************************************************/
Bool HandleDownload(char* ptr, long len)
{
    char* start = ptr;
    WORD i;
    DownloadInfo* dinfo;

    dinfo = (DownloadInfo*)ZeroSafeMalloc(sizeof(DownloadInfo));

    Extract(&ptr, &dinfo->num_files, 2);
    len -= 2;
    len = ExtractString(&ptr, len, dinfo->machine, MAX_HOSTNAME);
    len = ExtractString(&ptr, len, dinfo->path, MAX_PATH);
    len = ExtractString(&ptr, len, dinfo->reason, MAX_TEXT_REASON);
    len = ExtractString(&ptr, len, dinfo->demoPath, MAX_PATH);
    dinfo->files = (DownloadFileInfo*)ZeroSafeMalloc(sizeof(DownloadFileInfo) * dinfo->num_files);
    for (i = 0; i < dinfo->num_files; i++)
    {
        DownloadFileInfo* info = &dinfo->files[i];

        Extract(&ptr, &info->time, 4);
        Extract(&ptr, &info->flags, 4);
        Extract(&ptr, &info->size, 4);
        len -= 3 * 4;
        len = ExtractString(&ptr, len, info->filename, FILENAME_MAX);
    }

    if (len != 0)
    {
        SafeFree(dinfo->files);
        SafeFree(dinfo);
        return False;
    }

    DownloadFiles(dinfo);
    return True;
}
/********************************************************************/
Bool HandleNoCredits(char* ptr, long len)
{
    if (len != 0)
        return False;
    LoginError(IDS_NOCREDITS);
    return True;
}
/********************************************************************/
Bool HandlePasswordOk(char* ptr, long len)
{
    if (len != 0)
        return False;
    GameMessage(GetString(hInst, IDS_PASSWORDCHANGED));
    return True;
}
/********************************************************************/
Bool HandlePasswordNotOk(char* ptr, long len)
{
    if (len != 0)
        return False;
    GameMessage(GetString(hInst, IDS_PASSWORDNOTCHANGED));
    return True;
}
/********************************************************************/
Bool HandleCredits(char* ptr, long len)
{
    DWORD credits;

    if (len != sizeof(credits))
        return False;

    Extract(&ptr, &credits, 4);
    //   SetCredits(credits);
    return True;
}
/********************************************************************/
Bool HandleDeleteRsc(char* ptr, long len)
{
    list_type files = NULL;
    char* file;
    WORD num_files;
    int i;

    Extract(&ptr, &num_files, 2);
    len -= 2;

    for (i = 0; i < num_files; i++)
    {
        file = (char*)SafeMalloc(MAXMESSAGE + 1);
        if ((len = ExtractString(&ptr, len, file, MAXMESSAGE)) == -1)
        {
            list_destroy(files);
            return False;
        }
        files = list_add_item(files, file);
    }

    if (len == 0)
        DeleteRscFiles(files);
    list_destroy(files);

    return len == 0;
}
/********************************************************************/
Bool HandleDeleteAllRsc(char* ptr, long len)
{
    if (len != 0)
        return False;
    DeleteAllRscFiles();
    return True;
}

/********************************************************************/
Bool HandleLoginResync(char* ptr, long len)
{
    if (len != 0)
        return False;
    /* Go into resynchronization */
    MainSetState(STATE_STARTUP);
    return True;
}
/********************************************************************/
Bool HandleGameResync(char* ptr, long len)
{
    if (len != 0)
        return False;
    GameDisplayResync();
    /* Go into resynchronization */
    GameSetState(GAME_RESYNC);
    return True;
}
/********************************************************************/
Bool HandleNoCharacters(char* ptr, long len)
{
    if (len != 0)
        return False;
    LoginError(IDS_NOCHARACTERS);
    Logoff();
    return True;
}
/********************************************************************/
Bool HandleGetClient(char* ptr, long len)
{
    debug(("Protocol AP_GETCLIENT no longer supported!"));

    return True;
}
/********************************************************************/
Bool HandleClientPatch(char* ptr, long len)
{
    char patchhost[MAXMESSAGE], patchcachepath[MAXMESSAGE], patchpath[MAXMESSAGE];
    char cachefile[MAXMESSAGE], clubfile[MAXMESSAGE], reason[MAXMESSAGE];
    debug(("Got ClientPatch\n"));

    if ((len = ExtractString(&ptr, len, patchhost, MAXMESSAGE)) == -1)
        return False;
    if ((len = ExtractString(&ptr, len, patchpath, MAXMESSAGE)) == -1)
        return False;
    if ((len = ExtractString(&ptr, len, patchcachepath, MAXMESSAGE)) == -1)
        return False;
    if ((len = ExtractString(&ptr, len, cachefile, MAXMESSAGE)) == -1)
        return False;
    if ((len = ExtractString(&ptr, len, clubfile, MAXMESSAGE)) == -1)
        return False;
    if ((len = ExtractString(&ptr, len, reason, MAXMESSAGE)) == -1)
        return False;

    DownloadClientPatch(patchhost, patchpath, patchcachepath, cachefile,
        clubfile, reason);

    return True;
}
/********************************************************************/
Bool HandleResetView(char* ptr, long len)
{
    SetPlayerRemoteView(0, 0, 0, 0);
    return True;
}
/********************************************************************/
Bool HandleSetView(char* ptr, long len)
{
    char* start = ptr;
    ID objID;
    int viewFlags;
    int viewHeight;
    BYTE viewLight;

    Extract(&ptr, &objID, SIZE_ID);
    Extract(&ptr, &viewFlags, 4);
    Extract(&ptr, &viewHeight, 4);
    Extract(&ptr, &viewLight, 1);

    len -= (ptr - start);
    if (len != 0)
        return False;

    SetPlayerRemoteView(objID, viewFlags, viewHeight, viewLight);
    return True;
}

/********************************************************************/
// Missing function implementations
void ChangeObjectFlags(object_node *o)
{
    // This function should update the object flags in the game state
    // For now, just a stub implementation
}

void PingGotReplyUDP(void)
{
    // This function should handle UDP ping replies
    // For now, just a stub implementation
}

void SetMovementSpeedPct(int speed)
{
    // This function should set the player's movement speed percentage
    // For now, just a stub implementation
}
