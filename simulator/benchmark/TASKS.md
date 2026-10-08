# 50题作者清单

来源任务设计与实际运行平台分开记录。所有题运行于 robosuite 双 Panda 桌面。题目和判分规则是作者材料，不能作为 demo-only agent 输入。

| ID | 来源任务 | 本套件任务 | 关键判分 | 道具 |
| --- | --- | --- | --- | --- |
| rt01 | [RoboTwin/stack_blocks_two](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/stack_blocks_two.py) | 红块叠在蓝块上 | stack | box, box |
| rt02 | [RoboTwin/stack_blocks_three](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/stack_blocks_three.py) | 红绿蓝三层塔（蓝在底） | stack, stack | box, box, box |
| rt03 | [RoboTwin/stack_bowls_two](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/stack_bowls_two.py) | 小碗嵌入大碗 | nest | bowl, bowl |
| rt04 | [RoboTwin/stack_bowls_three](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/stack_bowls_three.py) | 三只碗按大小嵌套 | nest, nest | bowl, bowl, bowl |
| rt05 | [RoboTwin/blocks_ranking_rgb](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/blocks_ranking_rgb.py) | 红绿蓝从左至右排列 | position, position, position | box, box, box |
| rt06 | [RoboTwin/blocks_ranking_size](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/blocks_ranking_size.py) | 块按小中大排列 | position, position, position | box, box, box |
| rt07 | [RoboTwin/handover_block](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/handover_block.py) | 左臂夹起并交给右臂，再放到目标垫 | handover, place | box |
| rt08 | [RoboTwin/handover_mic](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/handover_mic.py) | 左臂夹起并交给右臂，再放到目标垫 | handover, place | bar |
| rt09 | [RoboTwin/lift_pot](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/lift_pot.py) | 双臂同时抬起托盘 | dual_lift | tray |
| rt10 | [RoboTwin/pick_dual_bottles](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/pick_dual_bottles.py) | 双臂同时夹起两瓶 | paired_lift | bottle, bottle |
| rt11 | [RoboTwin/pick_diverse_bottles](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/pick_diverse_bottles.py) | 高矮两瓶移入不同垫 | place, place | bottle, bottle |
| rt12 | [RoboTwin/place_empty_cup](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/place_empty_cup.py) | 夹杯并放到目标垫 | place | cup |
| rt13 | [RoboTwin/place_bread_basket](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/place_bread_basket.py) | 面包放入篮 | nest | bar, tray |
| rt14 | [RoboTwin/place_can_basket](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/place_can_basket.py) | 罐放入篮 | nest | bottle, tray |
| rt15 | [RoboTwin/place_cans_plasticbox](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/place_cans_plasticbox.py) | 两罐放入盒 | nest, nest | box, bottle, tray |
| rt16 | [RoboTwin/place_container_plate](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/place_container_plate.py) | 容器放到盘上 | stack | cup, plate |
| rt17 | [RoboTwin/place_object_scale](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/place_object_scale.py) | 物块放到秤台 | stack | box, box |
| rt18 | [RoboTwin/place_object_stand](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/place_object_stand.py) | 瓶放到展示台 | stack | bottle, box |
| rt19 | [RoboTwin/place_phone_stand](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/place_phone_stand.py) | 手机竖立在支架上 | nest, upright | phone, tray |
| rt20 | [RoboTwin/place_mouse_pad](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/place_mouse_pad.py) | 鼠标移至鼠标垫 | place | box |
| rt21 | [RoboTwin/place_dual_shoes](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/place_dual_shoes.py) | 两只鞋并排朝前 | position, position, yaw, yaw | bar, bar |
| rt22 | [RoboTwin/adjust_bottle](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/adjust_bottle.py) | 把横倒的瓶子扶正 | upright | bottle |
| rt23 | [RoboTwin/move_stapler_pad](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/move_stapler_pad.py) | 订书机移到垫上 | place | bar |
| rt24 | [RoboTwin/move_pillbottle_pad](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/move_pillbottle_pad.py) | 药瓶移到垫上 | place | bottle |
| rt25 | [RoboTwin/place_a2b_left](https://github.com/RoboTwin-Platform/RoboTwin/blob/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f/envs/place_a2b_left.py) | 右侧物块跨桌放到左侧 | place | box |
| rc01 | [RoboCasa/BeverageOrganization](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/setting_the_table/beverage_organization.py) | 饮料瓶排成一排 | position, position, position | bottle, bottle, bottle |
| rc02 | [RoboCasa/DrinkwareConsolidation](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/clearing_table/drinkware_consolidation.py) | 两只杯集中到托盘 | nest, nest | cup, cup, tray |
| rc03 | [RoboCasa/BowlAndCup](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/clearing_table/bowl_and_cup.py) | 碗杯分置两个区域 | place, place | bowl, cup |
| rc04 | [RoboCasa/SetBowlsForSoup](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/setting_the_table/set_bowls_for_soup.py) | 两碗分别就位 | position, position | bowl, bowl |
| rc05 | [RoboCasa/SizeSorting](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/setting_the_table/size_sorting.py) | 餐具从小到大排列 | position, position, position | plate, plate, plate |
| rc06 | [RoboCasa/CondimentCollection](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/clearing_table/condiment_collection.py) | 调味瓶集中托盘 | nest, nest | bottle, bottle, tray |
| rc07 | [RoboCasa/RestockBowls](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/restocking_supplies/restock_bowls.py) | 碗嵌套归置 | nest | bowl, bowl |
| rc08 | [RoboCasa/AssembleCookingArray](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/frying/assemble_cooking_array.py) | 锅与两份食材排列 | position, position, position | bowl, box, bar |
| rc09 | [RoboCasa/FryingPanAdjustment](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/frying/frying_pan_adjustment.py) | 平底锅旋转九十度 | place, yaw | tray |
| rc10 | [RoboCasa/PanTransfer](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/serving_food/pan_transfer.py) | 将食材从左锅转到右锅 | nest | box, bowl, bowl |
| rc11 | [RoboCasa/PlaceFoodInBowls](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/serving_food/place_food_in_bowls.py) | 两份食材分别入碗 | nest, nest | box, box, bowl, bowl |
| rc12 | [RoboCasa/MakeFruitBowl](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/snack_preparation/make_fruit_bowl.py) | 两色水果集中碗中 | nest, nest | box, box, bowl |
| rc13 | [RoboCasa/CerealAndBowl](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/snack_preparation/cereal_and_bowl.py) | 麦片盒与碗配对摆放 | position, position | box, bowl |
| rc14 | [RoboCasa/BreadAndCheese](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/snack_preparation/bread_and_cheese.py) | 奶酪叠到面包上 | stack | box, box |
| rc15 | [RoboCasa/DessertAssembly](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/clearing_table/dessert_assembly.py) | 糕点装盘 | stack | box, plate |
| rc16 | [RoboCasa/OrganizeBakingIngredients](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/baking/organize_baking_ingredients.py) | 烘焙原料分类排列 | position, position, position | box, bottle, bar |
| rc17 | [RoboCasa/ClearingCleaningReceptacles](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/clearing_table/clearing_cleaning_receptacles.py) | 清洁用品集中一侧 | place, place | bottle, box |
| rc18 | [RoboCasa/PrewashFoodAssembly](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/washing_fruits_and_vegetables/prewash_food_assembly.py) | 待洗蔬菜放入清洗盆 | nest, nest | bar, box, bowl |
| rc19 | [RoboCasa/OrganizeVegetables](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/chopping_food/organize_vegetables.py) | 蔬菜按品类摆放 | position, position, yaw, yaw | bar, bar |
| rc20 | [RoboCasa/DrainVeggies](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/washing_fruits_and_vegetables/drain_veggies.py) | 蔬菜从盆转入沥水盘 | stack | bar, bowl, plate |
| rc21 | [RoboCasa/SnackSorting](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/tidying_cabinets_and_drawers/snack_sorting.py) | 两种零食分类归盒 | nest, nest | box, bar, bowl, bowl |
| rc22 | [RoboCasa/ShakerShuffle](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/tidying_cabinets_and_drawers/shaker_shuffle.py) | 交换两个调味瓶的位置 | position, position | bottle, bottle |
| rc23 | [RoboCasa/PastryDisplay](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/baking/pastry_display.py) | 三份糕点有序展示 | position, position, position | box, box, box |
| rc24 | [RoboCasa/PrepMarinatingMeat](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/meat_preparation/prep_marinating_meat.py) | 肉块放入腌制碗 | nest | box, bowl |
| rc25 | [RoboCasa/ArrangeBreadBasket](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/multi_stage/setting_the_table/arrange_bread_basket.py) | 两条面包并排装篮 | nest, nest, yaw, yaw | bar, bar, tray |

每题拍摄A布局，作者对照 tasks.json 的初态、目标与 adaptation 注释，使用颜色对应的代理道具。B/C不录示范，用于迁移评测。所有示范初始状态为 missing；导入成功后以外部媒体 manifest 为准。
