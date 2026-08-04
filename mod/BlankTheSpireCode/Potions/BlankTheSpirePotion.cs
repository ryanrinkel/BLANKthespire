using BaseLib.Abstracts;
using BaseLib.Utils;
using BlankTheSpire.BlankTheSpireCode.Character;

namespace BlankTheSpire.BlankTheSpireCode.Potions;

[Pool(typeof(BlankTheSpirePotionPool))]
public abstract class BlankTheSpirePotion : CustomPotionModel;