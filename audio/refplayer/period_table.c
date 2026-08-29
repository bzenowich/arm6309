/* The ProTracker period table — 16 finetunes x 36 notes (C-1..B-3).
 *
 * audio/docs/modplayer.md §5.4 and §11 item 4: this table is COPIED, never computed.
 * ProTracker's values are hand-rounded and the roundings are not consistent, so
 * there is no formula that reproduces them. Two things go wrong if you try:
 *
 *   - 229 of 576 entries (40 %) come out different, worst case 16 cents at
 *     ft+7 B-3, which is plainly audible;
 *   - and all 229 of those are periods that do not exist anywhere in their own
 *     finetune row, so a tone portamento (3xx) walks toward a target it can
 *     never land on and the slide never terminates.
 *
 * 86 of the 384 octave relations in this table are not floor(x/2) either, which
 * is the same fact from another angle: the octaves were rounded independently.
 *
 * PROVENANCE
 *   Primary:   pt2-clone (8bitbubsy), src/pt2_tables.c,
 *              `const int16_t periodTable[(37*16)+15]` — a faithful C
 *              reimplementation of ProTracker 2.3D. Its rows carry a trailing
 *              0 sentinel (37 per row); that sentinel is dropped here.
 *   Confirmed: the finetune-0 row byte-for-byte against libopenmpt 0.4.4 and
 *              libmodplug 1.0.0 as installed on the build machine — two
 *              implementations independent of the primary source and of each
 *              other.
 *
 * VALIDATED, and re-checked at runtime by test_refplayer.c so an edit here
 * cannot silently corrupt it:
 *   - 16 rows of 36, every row strictly decreasing;
 *   - every entry within 1.41 of 856 / 2^(ft/96) / 2^(note/12), i.e. the
 *     deviations are roundings and not transcription errors;
 *   - row ft-8 is exactly [907] followed by ft0[0..34] — finetune -8 is one
 *     whole semitone flat, so the two rows must coincide, and they do.
 *
 * Row order is the file's own: index 0..7 are finetune 0..+7, index 8..15 are
 * finetune -8..-1. That is the low nibble of the sample header's finetune byte
 * read as-is, which is why audio/docs/modplayer.md §3 says to copy the nibble and not
 * to sign-extend it.
 */

#include "mod.h"

const uint16_t mod_protracker_period_table[16][36] = {
    /* finetune +0 */
    {
     856,  808,  762,  720,  678,  640,  604,  570,  538,  508,  480,  453,
     428,  404,  381,  360,  339,  320,  302,  285,  269,  254,  240,  226,
     214,  202,  190,  180,  170,  160,  151,  143,  135,  127,  120,  113,
    },
    /* finetune +1 */
    {
     850,  802,  757,  715,  674,  637,  601,  567,  535,  505,  477,  450,
     425,  401,  379,  357,  337,  318,  300,  284,  268,  253,  239,  225,
     213,  201,  189,  179,  169,  159,  150,  142,  134,  126,  119,  113,
    },
    /* finetune +2 */
    {
     844,  796,  752,  709,  670,  632,  597,  563,  532,  502,  474,  447,
     422,  398,  376,  355,  335,  316,  298,  282,  266,  251,  237,  224,
     211,  199,  188,  177,  167,  158,  149,  141,  133,  125,  118,  112,
    },
    /* finetune +3 */
    {
     838,  791,  746,  704,  665,  628,  592,  559,  528,  498,  470,  444,
     419,  395,  373,  352,  332,  314,  296,  280,  264,  249,  235,  222,
     209,  198,  187,  176,  166,  157,  148,  140,  132,  125,  118,  111,
    },
    /* finetune +4 */
    {
     832,  785,  741,  699,  660,  623,  588,  555,  524,  495,  467,  441,
     416,  392,  370,  350,  330,  312,  294,  278,  262,  247,  233,  220,
     208,  196,  185,  175,  165,  156,  147,  139,  131,  124,  117,  110,
    },
    /* finetune +5 */
    {
     826,  779,  736,  694,  655,  619,  584,  551,  520,  491,  463,  437,
     413,  390,  368,  347,  328,  309,  292,  276,  260,  245,  232,  219,
     206,  195,  184,  174,  164,  155,  146,  138,  130,  123,  116,  109,
    },
    /* finetune +6 */
    {
     820,  774,  730,  689,  651,  614,  580,  547,  516,  487,  460,  434,
     410,  387,  365,  345,  325,  307,  290,  274,  258,  244,  230,  217,
     205,  193,  183,  172,  163,  154,  145,  137,  129,  122,  115,  109,
    },
    /* finetune +7 */
    {
     814,  768,  725,  684,  646,  610,  575,  543,  513,  484,  457,  431,
     407,  384,  363,  342,  323,  305,  288,  272,  256,  242,  228,  216,
     204,  192,  181,  171,  161,  152,  144,  136,  128,  121,  114,  108,
    },
    /* finetune -8 */
    {
     907,  856,  808,  762,  720,  678,  640,  604,  570,  538,  508,  480,
     453,  428,  404,  381,  360,  339,  320,  302,  285,  269,  254,  240,
     226,  214,  202,  190,  180,  170,  160,  151,  143,  135,  127,  120,
    },
    /* finetune -7 */
    {
     900,  850,  802,  757,  715,  675,  636,  601,  567,  535,  505,  477,
     450,  425,  401,  379,  357,  337,  318,  300,  284,  268,  253,  238,
     225,  212,  200,  189,  179,  169,  159,  150,  142,  134,  126,  119,
    },
    /* finetune -6 */
    {
     894,  844,  796,  752,  709,  670,  632,  597,  563,  532,  502,  474,
     447,  422,  398,  376,  355,  335,  316,  298,  282,  266,  251,  237,
     223,  211,  199,  188,  177,  167,  158,  149,  141,  133,  125,  118,
    },
    /* finetune -5 */
    {
     887,  838,  791,  746,  704,  665,  628,  592,  559,  528,  498,  470,
     444,  419,  395,  373,  352,  332,  314,  296,  280,  264,  249,  235,
     222,  209,  198,  187,  176,  166,  157,  148,  140,  132,  125,  118,
    },
    /* finetune -4 */
    {
     881,  832,  785,  741,  699,  660,  623,  588,  555,  524,  494,  467,
     441,  416,  392,  370,  350,  330,  312,  294,  278,  262,  247,  233,
     220,  208,  196,  185,  175,  165,  156,  147,  139,  131,  123,  117,
    },
    /* finetune -3 */
    {
     875,  826,  779,  736,  694,  655,  619,  584,  551,  520,  491,  463,
     437,  413,  390,  368,  347,  328,  309,  292,  276,  260,  245,  232,
     219,  206,  195,  184,  174,  164,  155,  146,  138,  130,  123,  116,
    },
    /* finetune -2 */
    {
     868,  820,  774,  730,  689,  651,  614,  580,  547,  516,  487,  460,
     434,  410,  387,  365,  345,  325,  307,  290,  274,  258,  244,  230,
     217,  205,  193,  183,  172,  163,  154,  145,  137,  129,  122,  115,
    },
    /* finetune -1 */
    {
     862,  814,  768,  725,  684,  646,  610,  575,  543,  513,  484,  457,
     431,  407,  384,  363,  342,  323,  305,  288,  272,  256,  242,  228,
     216,  203,  192,  181,  171,  161,  152,  144,  136,  128,  121,  114,
    },
};
